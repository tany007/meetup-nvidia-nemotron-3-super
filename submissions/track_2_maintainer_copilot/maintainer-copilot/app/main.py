
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.github_client import discover_repo_docs, fetch_repo_issue, fetch_repo_issues, fetch_repo_labels, fetch_repo_readme
from app.nemotron_client import analyze_issue_with_nemotron, answer_contributor_question_with_nemotron
from app.vector_store import get_stored_issue, search_similar_issues, store_issue
from app.document_ingestion import ingest_document
from app.document_store import search_docs
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Maintainer Copilot",
    description="AI-powered assistant for open-source maintainers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IssueAnalysisRequest(BaseModel):
    title: str
    body: str = ""
    labels: list[str] = []
    readme_context: str | None = None

@app.get("/")
def root():
    return {
        "name": "Maintainer Copilot API",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "features": [
            "GitHub issue polling",
            "README and label fetching",
            "Nemotron issue analysis",
            "ChromaDB semantic issue memory",
            "memory-aware RAG triage",
        ],
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/github/{owner}/{repo}/issues")
def get_github_issues(owner: str, repo: str, state: str = "open"):
    repo_full_name = f"{owner}/{repo}"
    issues = fetch_repo_issues(repo_full_name=repo_full_name, state=state)

    return {
        "repository": repo_full_name,
        "state": state,
        "count": len(issues),
        "issues": issues,
    }


@app.get("/github/{owner}/{repo}/readme")
def get_github_readme(owner: str, repo: str):
    repo_full_name = f"{owner}/{repo}"
    readme = fetch_repo_readme(repo_full_name=repo_full_name)

    return readme


@app.get("/github/{owner}/{repo}/labels")
def get_github_labels(owner: str, repo: str):
    repo_full_name = f"{owner}/{repo}"
    labels = fetch_repo_labels(repo_full_name=repo_full_name)

    return {
        "repository": repo_full_name,
        "count": len(labels),
        "labels": labels,
    }

@app.get("/github/{owner}/{repo}/issues/{issue_number}")
def get_github_issue(owner: str, repo: str, issue_number: int):
    repo_full_name = f"{owner}/{repo}"

    try:
        issue = fetch_repo_issue(
            repo_full_name=repo_full_name,
            issue_number=issue_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API request failed: {exc}") from exc

    return {
        "repository": repo_full_name,
        "issue": issue,
    }


@app.post("/github/{owner}/{repo}/issues/{issue_number}/analyze")
def analyze_github_issue(
    owner: str,
    repo: str,
    issue_number: int,
    force_refresh: bool = False,
):
    repo_full_name = f"{owner}/{repo}"

    try:
        issue = fetch_repo_issue(
            repo_full_name=repo_full_name,
            issue_number=issue_number,
        )

        cached_issue = get_stored_issue(issue_id=issue["id"])

        if cached_issue and not force_refresh:
            cached_metadata = cached_issue["metadata"]

            return {
                "repository": repo_full_name,
                "issue": {
                    "id": issue["id"],
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "labels": issue["labels"],
                    "html_url": issue["html_url"],
                },
                "analysis": analysis_from_metadata(cached_metadata),
                "model": cached_metadata.get("analysis_model", "unknown"),
                "stored_in_memory": True,
                "cache_hit": True,
                "similar_issues_used": 0,
                "duplicate_candidates": [],
                "similar_issues": None,
            }

        labels = fetch_repo_labels(repo_full_name=repo_full_name)
        readme = fetch_repo_readme(repo_full_name=repo_full_name)

        label_names = [label["name"] for label in labels]
        readme_context = readme.get("content", "")[:4000] if readme.get("found") else ""

        search_query = build_issue_search_query(
            title=issue["title"],
            body=issue["body"],
        )
        similar_results = search_similar_issues(query=search_query, limit=3)

        relevant_similar_issues = build_relevant_similar_issues(
            results=similar_results,
            current_issue_id=issue["id"],
            max_items=3,
            max_distance=1.0,
        )

        duplicate_candidates = build_duplicate_candidates(
            results=similar_results,
            current_issue_id=issue["id"],
            current_title=issue["title"],
            max_items=3,
            min_similarity_score=0.5,
        )

        similar_issues_context = format_similar_issues_for_prompt(similar_results)

        result = analyze_issue_with_nemotron(
            title=issue["title"],
            body=issue["body"],
            labels=label_names,
            readme_context=readme_context,
            similar_issues_context=similar_issues_context,
        )

        analysis = result["analysis"]

        module_intelligence = analysis.get("module_intelligence", {})

        metadata = {
            "repository": repo_full_name,
            "issue_number": issue["number"],
            "issue_url": issue["html_url"],
            "state": issue["state"],
            "current_labels": ", ".join(issue["labels"]),
            "issue_type": analysis.get("issue_type", "unknown"),
            "severity": analysis.get("severity", "unknown"),
            "probable_module": analysis.get("probable_module", "unknown"),
            "probable_subsystem": module_intelligence.get("probable_subsystem", "unknown"),
            "component_ownership": module_intelligence.get("component_ownership", "unknown"),
            "affected_area": module_intelligence.get("affected_area", "unknown"),
            "suggested_labels": ", ".join(analysis.get("suggested_labels", [])),
            "duplicate_candidates": ", ".join(
                str(candidate)
                for candidate in analysis.get("duplicate_candidates", [])
            ),
            "missing_information": ", ".join(
                analysis.get("missing_information", [])
            ),
            "analysis_summary": analysis.get("summary", ""),
            "analysis_reasoning": analysis.get("reasoning", ""),
            "analysis_model": result["model"],
        }

        if analysis["severity"] != "unknown":
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
                    "issue_type": analysis.get("issue_type", "unknown"),
                    "severity": analysis.get("severity", "unknown"),
                    "probable_module": analysis.get("probable_module", "unknown"),
                    "suggested_labels": ", ".join(analysis.get("suggested_labels", [])),
                    "duplicate_candidates": ", ".join(
                        str(candidate)
                        for candidate in analysis.get("duplicate_candidates", [])
                    ),
                    "missing_information": ", ".join(
                        analysis.get("missing_information", [])
                    ),
                    "analysis_summary": analysis.get("summary", ""),
                    "analysis_reasoning": analysis.get("reasoning", ""),
                    "analysis_model": result["model"],
                },
            )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Issue analysis failed: {exc}") from exc

    return {
        "repository": repo_full_name,
        "issue": {
            "id": issue["id"],
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "labels": issue["labels"],
            "html_url": issue["html_url"],
        },
        "analysis": analysis,
        "model": result["model"],
        "stored_in_memory": analysis["severity"] != "unknown",
        "cache_hit": False,
        "similar_issues_used": len(relevant_similar_issues),
        "duplicate_candidates": duplicate_candidates,
        "similar_issues": relevant_similar_issues,
    }


@app.post("/issues/analyze")
def analyze_issue(request: IssueAnalysisRequest):
    try:
        search_query = build_issue_search_query(
            title=request.title,
            body=request.body,
        )
        similar_results = search_similar_issues(query=search_query, limit=3)

        duplicate_candidates = build_duplicate_candidates(
            results=similar_results,
            current_issue_id=None,
            current_title=request.title,
            max_items=3,
            min_similarity_score=0.5,
        )

        similar_issues_context = format_similar_issues_for_prompt(similar_results)

        result = analyze_issue_with_nemotron(
            title=request.title,
            body=request.body,
            labels=request.labels,
            readme_context=request.readme_context,
            similar_issues_context=similar_issues_context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Nemotron API request failed: {exc}") from exc

    return {
        "analysis": result["analysis"],
        "model": result["model"],
        "similar_issues_used": count_relevant_similar_issues(similar_results),
        "duplicate_candidates": duplicate_candidates,
        "similar_issues": similar_results,
    }

@app.get("/issues/search")
def search_issues(query: str, limit: int = 5):
    results = search_similar_issues(query=query, limit=limit)

    return {
        "query": query,
        "results": results,
    }


def build_issue_search_query(title: str, body: str) -> str:
    return f"{title}\n\n{body}".strip()


def format_similar_issues_for_prompt(
    results: dict,
    max_items: int = 3,
    max_distance: float = 1.0,
) -> str:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not documents:
        return ""

    formatted_issues = []

    for index, document in enumerate(documents[:max_items]):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None and distance > max_distance:
            continue

        similarity_score = distance_to_similarity_score(distance)
        confidence = confidence_from_similarity_score(similarity_score)

        formatted_issues.append(
            "\n".join(
                [
                    f"Similar issue #{len(formatted_issues) + 1}:",
                    f"Repository: {metadata.get('repository', 'unknown')}",
                    f"Issue number: {metadata.get('issue_number', 'unknown')}",
                    f"Issue type: {metadata.get('issue_type', 'unknown')}",
                    f"Severity: {metadata.get('severity', 'unknown')}",
                    f"Probable module: {metadata.get('probable_module', 'unknown')}",
                    f"Suggested labels: {metadata.get('suggested_labels', '')}",
                    f"Summary: {metadata.get('analysis_summary', '')}",
                    f"Distance: {distance}",
                    f"Similarity score: {similarity_score}",
                    f"Duplicate confidence: {confidence}",
                    f"Excerpt: {document[:500]}",
                ]
            )
        )

    return "\n\n---\n\n".join(formatted_issues)

def count_relevant_similar_issues(results: dict, max_distance: float = 1.0) -> int:
    distances = results.get("distances", [[]])[0]

    return sum(
        1
        for distance in distances
        if distance is not None and distance <= max_distance
    )

def split_metadata_list(value: str | None) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def split_metadata_int_list(value: str | None) -> list[int]:
    if not value:
        return []

    candidates = []

    for item in value.split(","):
        item = item.strip()

        if item.isdigit():
            candidates.append(int(item))

    return candidates

def analysis_from_metadata(metadata: dict) -> dict:
    return {
        "issue_type": metadata.get("issue_type", "unknown"),
        "severity": metadata.get("severity", "unknown"),
        "module_intelligence": {
            "probable_subsystem": metadata.get("probable_subsystem", "unknown"),
            "component_ownership": metadata.get("component_ownership", "unknown"),
            "affected_area": metadata.get("affected_area", "unknown"),
        },
        "probable_module": metadata.get("probable_module", "unknown"),
        "suggested_labels": split_metadata_list(metadata.get("suggested_labels")),
        "duplicate_candidates": split_metadata_int_list(metadata.get("duplicate_candidates")),
        "missing_information": split_metadata_list(metadata.get("missing_information")),
        "summary": metadata.get("analysis_summary", ""),
        "reasoning": metadata.get("analysis_reasoning", ""),
    }

def distance_to_similarity_score(distance: float | None) -> float:
    if distance is None:
        return 0.0

    score = 1 / (1 + distance)

    return round(score, 3)


def confidence_from_similarity_score(score: float) -> str:
    if score >= 0.75:
        return "high"

    if score >= 0.5:
        return "medium"

    return "low"


def build_duplicate_reasoning(
    current_title: str,
    candidate_metadata: dict,
    similarity_score: float,
) -> str:
    issue_number = candidate_metadata.get("issue_number", "unknown")
    probable_module = candidate_metadata.get("probable_module", "unknown")
    summary = candidate_metadata.get("analysis_summary", "")

    if similarity_score >= 0.75:
        return (
            f"Possible duplicate of issue #{issue_number}; both issues appear related "
            f"to {probable_module}. Prior summary: {summary}"
        ).strip()

    if similarity_score >= 0.5:
        return (
            f"Potentially related to issue #{issue_number}; similarity is moderate. "
            f"Prior summary: {summary}"
        ).strip()

    return (
        f"Weak similarity to issue #{issue_number}; likely related only at a broad topic level."
    )


def build_duplicate_candidates(
    results: dict,
    current_issue_id: int | None = None,
    current_title: str = "",
    max_items: int = 3,
    min_similarity_score: float = 0.5,
) -> list[dict]:
    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    candidates = []

    for index, candidate_id in enumerate(ids[:max_items]):
        if current_issue_id is not None and str(candidate_id) == str(current_issue_id):
            continue

        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        similarity_score = distance_to_similarity_score(distance)

        if similarity_score < min_similarity_score:
            continue

        candidates.append(
            {
                "issue_number": metadata.get("issue_number"),
                "issue_url": metadata.get("issue_url", ""),
                "repository": metadata.get("repository", ""),
                "similarity_score": similarity_score,
                "confidence": confidence_from_similarity_score(similarity_score),
                "reasoning": build_duplicate_reasoning(
                    current_title=current_title,
                    candidate_metadata=metadata,
                    similarity_score=similarity_score,
                ),
            }
        )

    return candidates

def build_relevant_similar_issues(
    results: dict,
    current_issue_id: int | None = None,
    max_items: int = 3,
    max_distance: float = 1.0,
) -> list[dict]:
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    relevant_issues = []

    for index, candidate_id in enumerate(ids[:max_items]):
        if current_issue_id is not None and str(candidate_id) == str(current_issue_id):
            continue

        distance = distances[index] if index < len(distances) else None

        if distance is not None and distance > max_distance:
            continue

        metadata = metadatas[index] if index < len(metadatas) else {}
        document = documents[index] if index < len(documents) else ""
        similarity_score = distance_to_similarity_score(distance)

        relevant_issues.append(
            {
                "id": candidate_id,
                "repository": metadata.get("repository", ""),
                "issue_number": metadata.get("issue_number"),
                "issue_url": metadata.get("issue_url", ""),
                "issue_type": metadata.get("issue_type", "unknown"),
                "severity": metadata.get("severity", "unknown"),
                "probable_module": metadata.get("probable_module", "unknown"),
                "summary": metadata.get("analysis_summary", ""),
                "distance": distance,
                "similarity_score": similarity_score,
                "confidence": confidence_from_similarity_score(similarity_score),
                "excerpt": document[:500],
            }
        )

    return relevant_issues


class ContributorQuestionRequest(BaseModel):
    question: str
    limit: int = 5

def format_retrieved_context_for_contributor(results: dict, max_distance: float = 1.2) -> str:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    context_items = []

    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None and distance > max_distance:
            continue

        context_items.append(
            "\n".join(
                [
                    f"Issue number: {metadata.get('issue_number', 'unknown')}",
                    f"Repository: {metadata.get('repository', 'unknown')}",
                    f"URL: {metadata.get('issue_url', '')}",
                    f"Type: {metadata.get('issue_type', 'unknown')}",
                    f"Severity: {metadata.get('severity', 'unknown')}",
                    f"Module: {metadata.get('probable_module', 'unknown')}",
                    f"Subsystem: {metadata.get('probable_subsystem', 'unknown')}",
                    f"Component ownership: {metadata.get('component_ownership', 'unknown')}",
                    f"Affected area: {metadata.get('affected_area', 'unknown')}",
                    f"Summary: {metadata.get('analysis_summary', '')}",
                    f"Distance: {distance}",
                    "Issue excerpt:",
                    document[:1000],
                ]
            )
        )

    return "\n\n---\n\n".join(context_items)


@app.post("/contributors/ask")
def ask_contributor_assistant(request: ContributorQuestionRequest):
    try:
        issue_results = search_similar_issues(
            query=request.question,
            limit=request.limit,
        )
        issue_context = format_retrieved_context_for_contributor(issue_results)

        doc_results = search_docs(
            query=request.question,
            limit=request.limit,
        )
        doc_context = format_doc_results_for_contributor(doc_results)

        combined_context = "\n\n===\n\n".join(
            filter(None, [doc_context, issue_context])
        )

        result = answer_contributor_question_with_nemotron(
            question=request.question,
            context=combined_context,
        )

    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Contributor assistant failed: {exc}") from exc

    return {
        "question": request.question,
        "answer": result["answer"],
        "model": result["model"],
        "retrieval": {
            "issue_results_count": len(issue_results.get("ids", [[]])[0]),
            "doc_results_count": len(doc_results.get("ids", [[]])[0]),
            "context_found": bool(combined_context),
        },
    }

@app.post("/github/{owner}/{repo}/ingest")
def ingest_repo_docs(owner: str, repo: str):
    repo_full_name = f"{owner}/{repo}"
    ingestion_summary = []

    docs = discover_repo_docs(repo_full_name=repo_full_name)

    if not docs:
        return {
            "repository": repo_full_name,
            "ingestion": [],
            "message": "No supported documentation files found.",
        }

    for doc in docs:
        try:
            chunks = ingest_document(
                repo_full_name=repo_full_name,
                source=doc["name"],
                content=doc["content"],
                extension=doc["extension"],
            )

            ingestion_summary.append({
                "source": doc["name"],
                "extension": doc["extension"],
                "status": "ingested",
                "chunks_stored": len(chunks),
                "chunks": chunks,
            })

        except Exception as exc:
            ingestion_summary.append({
                "source": doc["name"],
                "extension": doc["extension"],
                "status": "error",
                "error": str(exc),
                "chunks_stored": 0,
            })

    return {
        "repository": repo_full_name,
        "ingestion": ingestion_summary,
    }

def format_doc_results_for_contributor(results: dict, max_distance: float = 1.5) -> str:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    context_items = []

    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None and distance > max_distance:
            continue

        context_items.append(
            "\n".join(
                [
                    f"Source: {metadata.get('source', 'unknown')}",
                    f"Section: {metadata.get('section', 'unknown')}",
                    f"Repository: {metadata.get('repo_full_name', 'unknown')}",
                    f"Distance: {distance}",
                    "Content:",
                    document[:1000],
                ]
            )
        )

    return "\n\n---\n\n".join(context_items)

@app.get("/github/{owner}/{repo}/docs/search")
def search_repo_docs(owner: str, repo: str, query: str, limit: int = 5):
    repo_full_name = f"{owner}/{repo}"

    results = search_docs(
        query=query,
        repo_full_name=repo_full_name,
        limit=limit,
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    hits = [
        {
            "source": metadatas[i].get("source"),
            "section": metadatas[i].get("section"),
            "chunk_index": metadatas[i].get("chunk_index"),
            "chunk_total": metadatas[i].get("chunk_total"),
            "similarity_score": distance_to_similarity_score(distances[i]),
            "distance": distances[i],
            "excerpt": documents[i][:500],
        }
        for i in range(len(documents))
    ]

    return {
        "repository": repo_full_name,
        "query": query,
        "hits": hits,
    }
