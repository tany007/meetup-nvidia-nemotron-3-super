from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DB_PATH = "chroma_db"
COLLECTION_NAME = "github_issues"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)


def build_issue_document(title: str, body: str | None) -> str:
    body = body or ""

    return f"""
Title:
{title}

Body:
{body}
""".strip()


def store_issue(
    issue_id: int,
    title: str,
    body: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    document = build_issue_document(title=title, body=body)
    embedding = embedding_model.encode(document).tolist()

    collection.upsert(
        ids=[str(issue_id)],
        documents=[document],
        embeddings=[embedding],
        metadatas=[metadata or {}],
    )


def get_stored_issue(issue_id: int) -> dict[str, Any] | None:
    result = collection.get(
        ids=[str(issue_id)],
        include=["documents", "metadatas"],
    )

    ids = result.get("ids", [])

    if not ids:
        return None

    return {
        "id": ids[0],
        "document": result.get("documents", [None])[0],
        "metadata": result.get("metadatas", [{}])[0],
    }


def search_similar_issues(query: str, limit: int = 5) -> dict[str, Any]:
    query_embedding = embedding_model.encode(query).tolist()

    return collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
    )