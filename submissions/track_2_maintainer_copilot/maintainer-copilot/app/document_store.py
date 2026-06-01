from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DB_PATH = "chroma_db"
DOCS_COLLECTION_NAME = "repository_docs"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

docs_collection = chroma_client.get_or_create_collection(name=DOCS_COLLECTION_NAME)

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)


def build_chunk_id(repo_full_name: str, source: str, section: str, chunk_index: int) -> str:
    return f"{repo_full_name}::{source}::{section}::{chunk_index}"


def chunk_already_stored(chunk_id: str) -> bool:
    result = docs_collection.get(ids=[chunk_id])

    return bool(result.get("ids"))


def store_doc_chunk(
    repo_full_name: str,
    source: str,
    section: str,
    chunk_index: int,
    chunk_total: int,
    content: str,
    extra_metadata: dict[str, Any] | None = None,
) -> str:
    chunk_id = build_chunk_id(
        repo_full_name=repo_full_name,
        source=source,
        section=section,
        chunk_index=chunk_index,
    )

    if chunk_already_stored(chunk_id):
        return chunk_id

    embedding = embedding_model.encode(content).tolist()

    metadata = {
        "repo_full_name": repo_full_name,
        "source": source,
        "section": section,
        "chunk_index": chunk_index,
        "chunk_total": chunk_total,
        **(extra_metadata or {}),
    }

    docs_collection.upsert(
        ids=[chunk_id],
        documents=[content],
        embeddings=[embedding],
        metadatas=[metadata],
    )

    return chunk_id


def search_docs(
    query: str,
    repo_full_name: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    query_embedding = embedding_model.encode(query).tolist()

    where_filter = {"repo_full_name": repo_full_name} if repo_full_name else None

    return docs_collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        where=where_filter,
    )


def get_doc_chunks_by_source(
    repo_full_name: str,
    source: str,
) -> list[dict[str, Any]]:
    result = docs_collection.get(
        where={
            "$and": [
                {"repo_full_name": repo_full_name},
                {"source": source},
            ]
        },
        include=["documents", "metadatas"],
    )

    ids = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    return [
        {
            "id": ids[i],
            "content": documents[i],
            "metadata": metadatas[i],
        }
        for i in range(len(ids))
    ]