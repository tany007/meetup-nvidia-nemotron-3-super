import os
from typing import Any

from dotenv import load_dotenv
from github import Github
from github.GithubException import UnknownObjectException

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()

CANDIDATE_EXTENSIONS = [".md", ".adoc", ".rst", ".txt"]

SUPPORTED_DOC_NAMES = ["README", "CONTRIBUTING"]


def fetch_repo_file_any_extension(
    repo_full_name: str,
    base_name: str,
) -> dict[str, Any] | None:
    repo = get_repository(repo_full_name)

    for ext in CANDIDATE_EXTENSIONS:
        path = f"{base_name}{ext}"

        try:
            file_content = repo.get_contents(path)

            return {
                "path": path,
                "name": f"{base_name}{ext}",
                "extension": ext,
                "content": file_content.decoded_content.decode("utf-8", errors="replace"),
            }
        except UnknownObjectException:
            continue

    return None


def discover_repo_docs(repo_full_name: str) -> list[dict[str, Any]]:
    found_docs = []

    for base_name in SUPPORTED_DOC_NAMES:
        doc = fetch_repo_file_any_extension(
            repo_full_name=repo_full_name,
            base_name=base_name,
        )

        if doc:
            found_docs.append(doc)

    return found_docs


def get_repository(repo_full_name: str):
    return github_client.get_repo(repo_full_name)


def issue_to_dict(issue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "number": issue.number,
        "title": issue.title,
        "body": issue.body or "",
        "state": issue.state,
        "labels": [label.name for label in issue.labels],
        "html_url": issue.html_url,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }


def fetch_repo_issue(repo_full_name: str, issue_number: int) -> dict[str, Any]:
    repo = get_repository(repo_full_name)
    issue = repo.get_issue(number=issue_number)

    if issue.pull_request:
        raise ValueError(f"#{issue_number} is a pull request, not an issue")

    return issue_to_dict(issue)


def fetch_repo_issues(repo_full_name: str, state: str = "open") -> list[dict[str, Any]]:
    repo = get_repository(repo_full_name)
    issues = repo.get_issues(state=state)

    return [
        issue_to_dict(issue)
        for issue in issues
        if not issue.pull_request
    ]


def fetch_repo_readme(repo_full_name: str) -> dict[str, Any]:
    repo = get_repository(repo_full_name)

    try:
        readme = repo.get_readme()
    except UnknownObjectException:
        return {
            "repository": repo_full_name,
            "found": False,
            "content": "",
        }

    return {
        "repository": repo_full_name,
        "found": True,
        "name": readme.name,
        "path": readme.path,
        "html_url": readme.html_url,
        "content": readme.decoded_content.decode("utf-8", errors="replace"),
    }


def fetch_repo_labels(repo_full_name: str) -> list[dict[str, Any]]:
    repo = get_repository(repo_full_name)

    labels = repo.get_labels()

    return [
        {
            "name": label.name,
            "color": label.color,
            "description": label.description or "",
        }
        for label in labels
    ]


def fetch_repo_file(repo_full_name: str, path: str) -> str | None:
    repo = get_repository(repo_full_name)

    try:
        file_content = repo.get_contents(path)
        return file_content.decoded_content.decode("utf-8", errors="replace")
    except UnknownObjectException:
        return None