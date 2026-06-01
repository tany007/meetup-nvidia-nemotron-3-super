import hashlib
import hmac
import logging
import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, HTTPException, Request

from app.github_client import fetch_repo_issue, fetch_repo_labels, fetch_repo_readme
from app.nemotron_client import analyze_issue_with_nemotron
from app.vector_store import search_similar_issues, store_issue

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

HANDLED_ACTIONS = {"opened", "edited", "reopened"}


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

def verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 against the configured webhook secret."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET is not set — skipping signature validation")
        return True

    if not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def process_issue_event(payload: dict, repo_full_name: str) -> None:
    """
    Full pipeline run in the background:
      1. Fetch canonical issue data from GitHub API
      2. Generate embedding and store in Vector DB
      3. Search for duplicates
      4. Run Nemotron analysis and update stored metadata
    """
    issue_data = payload.get("issue", {})
    issue_number = issue_data.get("number")

    if not issue_number:
        logger.error("process_issue_event: missing issue number in payload")
        return

    # ── Step 1: Fetch canonical issue from GitHub API ──────────────────────
    try:
        issue = fetch_repo_issue(
            repo_full_name=repo_full_name,
            issue_number=issue_number,
        )
    except ValueError as exc:
        logger.warning("Skipping pull request received as issue event: %s", exc)
        return
    except Exception as exc:
        logger.error("Failed to fetch issue #%s from GitHub: %s", issue_number, exc)
        return

    # ── Step 2: Initial store — captures the issue in vector DB early ───────
    try:
        store_issue(
            issue_id=issue["id"],
            title=issue["title"],
            body=issue["body"],
            metadata={
                "repository": repo_full_name,
                "issue_number": issue["number"],
                "issue_url": issue["html_url"],
                "state": issue["state"],
                "current_labels": ", ".join(issue["labels"]),
                "github_action": payload.get("action", ""),
            },
        )
        logger.info("Stored issue #%s in vector DB", issue_number)
    except Exception as exc:
        logger.error("Failed to store issue #%s in vector DB: %s", issue_number, exc)
        return

    # ── Step 3: Duplicate search ────────────────────────────────────────────
    try:
        search_query = f"{issue['title']}\n\n{issue['body']}".strip()
        similar_results = search_similar_issues(query=search_query, limit=5)
        logger.info(
            "Duplicate search for issue #%s returned %d candidates",
            issue_number,
            len(similar_results.get("ids", [[]])[0]),
        )
    except Exception as exc:
        logger.error("Duplicate search failed for issue #%s: %s", issue_number, exc)
        similar_results = {}

    # ── Step 4: Nemotron analysis ───────────────────────────────────────────
    try:
        labels = fetch_repo_labels(repo_full_name=repo_full_name)
        readme = fetch_repo_readme(repo_full_name=repo_full_name)

        label_names = [label["name"] for label in labels]
        readme_context = readme.get("content", "")[:4000] if readme.get("found") else ""

        similar_issues_context = _format_similar_issues(similar_results)

        result = analyze_issue_with_nemotron(
            title=issue["title"],
            body=issue["body"],
            labels=label_names,
            readme_context=readme_context,
            similar_issues_context=similar_issues_context,
        )
        analysis = result["analysis"]
        logger.info(
            "Nemotron analysis complete for issue #%s — type=%s severity=%s",
            issue_number,
            analysis.get("issue_type"),
            analysis.get("severity"),
        )
    except Exception as exc:
        logger.error("Nemotron analysis failed for issue #%s: %s", issue_number, exc)
        return

    # ── Step 5: Re-store with enriched metadata ─────────────────────────────
    if analysis.get("severity", "unknown") != "unknown":
        try:
            module_intelligence = analysis.get("module_intelligence", {})

            store_issue(
                issue_id=issue["id"],
                title=issue["title"],
                body=issue["body"],
                metadata={
                    "repository": repo_full_name,
                    "issue_number": issue["number"],
                    "issue_url": issue["html_url"],
                    "state": issue["state"],
                    "current_labels": ", ".join(issue["labels"]),
                    "github_action": payload.get("action", ""),
                    "issue_type": analysis.get("issue_type", "unknown"),
                    "severity": analysis.get("severity", "unknown"),
                    "probable_module": analysis.get("probable_module", "unknown"),
                    "probable_subsystem": module_intelligence.get("probable_subsystem", "unknown"),
                    "component_ownership": module_intelligence.get("component_ownership", "unknown"),
                    "affected_area": module_intelligence.get("affected_area", "unknown"),
                    "suggested_labels": ", ".join(analysis.get("suggested_labels", [])),
                    "duplicate_candidates": ", ".join(
                        str(c) for c in analysis.get("duplicate_candidates", [])
                    ),
                    "missing_information": ", ".join(analysis.get("missing_information", [])),
                    "analysis_summary": analysis.get("summary", ""),
                    "analysis_reasoning": analysis.get("reasoning", ""),
                    "analysis_model": result["model"],
                },
            )
            logger.info("Re-stored enriched metadata for issue #%s", issue_number)
        except Exception as exc:
            logger.error("Failed to re-store enriched issue #%s: %s", issue_number, exc)


# ---------------------------------------------------------------------------
# Webhook entry point
# ---------------------------------------------------------------------------

async def handle_github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """
    Validates the GitHub webhook signature, filters relevant events,
    and dispatches background processing.
    """
    raw_body = await request.body()

    # Validate signature
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(raw_body, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse event type and action
    event_type = request.headers.get("X-GitHub-Event", "unknown")

    try:
        payload = request.json() if hasattr(request, "_json") else __import__("json").loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    action = payload.get("action", "")

    # Filter: only handle issue events with relevant actions
    if event_type != "issues" or action not in HANDLED_ACTIONS:
        logger.debug("Ignored webhook event=%s action=%s", event_type, action)
        return {"status": "ignored", "event": event_type, "action": action}

    repository = payload.get("repository", {})
    repo_full_name = repository.get("full_name", "")

    if not repo_full_name:
        raise HTTPException(status_code=400, detail="Missing repository full_name in payload")

    # Dispatch to background — respond immediately with 202
    background_tasks.add_task(process_issue_event, payload, repo_full_name)

    logger.info(
        "Webhook accepted: event=%s action=%s repo=%s issue=#%s",
        event_type,
        action,
        repo_full_name,
        payload.get("issue", {}).get("number"),
    )

    return {
        "status": "accepted",
        "event": event_type,
        "action": action,
        "repository": repo_full_name,
        "issue_number": payload.get("issue", {}).get("number"),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_similar_issues(results: dict, max_items: int = 3, max_distance: float = 1.0) -> str:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    formatted = []

    for index, document in enumerate(documents[:max_items]):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None and distance > max_distance:
            continue

        formatted.append(
            "\n".join([
                f"Similar issue #{len(formatted) + 1}:",
                f"Repository: {metadata.get('repository', 'unknown')}",
                f"Issue number: {metadata.get('issue_number', 'unknown')}",
                f"Issue type: {metadata.get('issue_type', 'unknown')}",
                f"Severity: {metadata.get('severity', 'unknown')}",
                f"Probable module: {metadata.get('probable_module', 'unknown')}",
                f"Summary: {metadata.get('analysis_summary', '')}",
                f"Distance: {distance}",
                f"Excerpt: {document[:500]}",
            ])
        )

    return "\n\n---\n\n".join(formatted)