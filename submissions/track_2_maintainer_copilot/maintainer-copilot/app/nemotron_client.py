import json
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NVIDIA_API_BASE_URL = os.getenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")


def build_issue_analysis_prompt(
    title: str,
    body: str,
    labels: list[str] | None = None,
    readme_context: str | None = None,
    similar_issues_context: str | None = None,
) -> str:
    labels = labels or []

    return f"""
Return ONLY valid JSON.
Do not include markdown.
Do not include explanation outside JSON.
Do not include code fences.

You are a maintainer assistant helping triage GitHub issues.

Analyze the GitHub issue below and return exactly this JSON shape:

{{
  "issue_type": "bug",
  "severity": "medium",
  "module_intelligence": {{
    "probable_subsystem": "streaming",
    "component_ownership": "websocket layer",
    "affected_area": "auth service"
  }},
  "probable_module": "streaming",
  "suggested_labels": ["bug", "webrtc"],
  "duplicate_candidates": [12, 27],
  "missing_information": ["browser version", "logs"],
  "summary": "One sentence summary.",
  "reasoning": "Brief explanation."
}}

Allowed issue_type values:
- bug
- enhancement
- documentation
- question
- maintenance
- unknown

Allowed severity values:
- low
- medium
- high
- critical

Severity guidance:
- critical: security issue, data loss, production outage, broken release
- high: major functionality broken or common workflow blocked
- medium: bug with workaround, misleading docs likely to cause production problems, limited feature broken
- low: docs typo, minor UX, enhancement, question

Rules:
- Use only valid JSON.
- Use double quotes for every JSON key and string.
- suggested_labels must be an array of strings.
- duplicate_candidates must be an array of issue numbers, not IDs.
- missing_information must be an array of short strings.
- Prefer labels from the existing repository labels when appropriate.
- If similar issues are provided, use them to identify possible duplicates.
- Treat high duplicate confidence as stronger evidence than medium or low confidence.
- Only include duplicate_candidates when similar issues are strongly related.
- Do not include weakly related issues as duplicates.
- Do not blindly copy labels from similar issues if they do not fit the current issue.
- If the issue is mainly documentation, use issue_type "documentation".
- Keep reasoning under 400 characters.

Module intelligence rules:
- probable_subsystem should identify the broad subsystem, for example "testing", "web", "security", "documentation", "data", "build", "configuration".
- component_ownership should identify the likely owning component/team area, for example "websocket layer", "auth service", "testcontainers integration", "rest client documentation".
- affected_area should describe the impacted runtime or user-facing area, for example "startup", "management port security", "integration tests", "HTTP client resource usage".
- If unsure, use "unknown".

Existing repository labels:
{labels}

Similar historical issues:
{similar_issues_context or "No similar historical issues found."}

README context:
{readme_context or "No README context provided."}

GitHub issue title:
{title}

GitHub issue body:
{body or "No body provided."}
""".strip()


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    return json.loads(match.group(0))


def call_nemotron(prompt: str) -> dict[str, Any]:
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is not configured")

    url = f"{NVIDIA_API_BASE_URL}/chat/completions"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": NEMOTRON_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You return only valid JSON. No markdown. No explanations outside JSON."
                        "Do not explain. DO not reason step by step. Do not use markdown"
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0,
            "max_tokens": 500,
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def analyze_issue_with_nemotron(
    title: str,
    body: str,
    labels: list[str] | None = None,
    readme_context: str | None = None,
    similar_issues_context: str | None = None,
) -> dict[str, Any]:
    prompt = build_issue_analysis_prompt(
        title=title,
        body=body,
        labels=labels,
        readme_context=readme_context,
        similar_issues_context=similar_issues_context,
    )

    raw_response = call_nemotron(prompt)

    content = raw_response["choices"][0]["message"]["content"]

    try:
        analysis = extract_json_object(content)
    except json.JSONDecodeError:
        analysis = {
            "issue_type": "unknown",
            "severity": "unknown",
            "module_intelligence": {
                "probable_subsystem": "unknown",
                "component_ownership": "unknown",
                "affected_area": "unknown",
            },
            "probable_module": "unknown",
            "suggested_labels": [],
            "duplicate_candidates": [],
            "missing_information": [],
            "summary": "Nemotron returned a non-JSON response.",
            "reasoning": content[:1000],
        }

    return {
        "analysis": analysis,
        "model": NEMOTRON_MODEL,
    }


def answer_contributor_question_with_nemotron(
    question: str,
    context: str,
) -> dict[str, Any]:
    prompt = f"""
Return ONLY valid JSON.
Do not include markdown.
Do not include explanation outside JSON.

You are a contributor assistant for an open-source repository.

Answer the contributor question using only the provided repository memory context.
If the answer is not supported by the context, say so clearly.

Return exactly this JSON shape:

{{
  "answer": "Clear, concise answer for the contributor.",
  "confidence": "low | medium | high",
  "referenced_issues": [123, 456],
  "reasoning": "Brief explanation of how the context supports the answer."
}}

Contributor question:
{question}

Repository memory context:
{context or "No relevant context found."}
""".strip()

    raw_response = call_nemotron(prompt)
    content = raw_response["choices"][0]["message"]["content"]

    try:
        answer = extract_json_object(content)
    except json.JSONDecodeError:
        answer = {
            "answer": content[:1000],
            "confidence": "low",
            "referenced_issues": [],
            "reasoning": "Nemotron returned a non-JSON response.",
        }

    return {
        "answer": answer,
        "model": NEMOTRON_MODEL,
    }