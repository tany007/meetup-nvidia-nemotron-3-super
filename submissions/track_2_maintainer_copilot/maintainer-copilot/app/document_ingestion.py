import re
from typing import Any

from app.document_store import store_doc_chunk

SUPPORTED_SOURCES = ["README.md", "CONTRIBUTING.md"]

MAX_CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 50

MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

ASCIIDOC_HEADING_PATTERN = re.compile(r"^(={1,4})\s+(.+)$", re.MULTILINE)

RST_HEADING_CHARS = set("#*=-^~")

HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def split_markdown_into_sections(content: str) -> list[dict[str, Any]]:
    sections = []
    heading_matches = list(MARKDOWN_HEADING_PATTERN.finditer(content))

    if not heading_matches:
        sections.append({"section": "content", "level": 0, "content": content.strip()})
        return sections

    for index, match in enumerate(heading_matches):
        heading_level = len(match.group(1))
        heading_text = match.group(2).strip()
        start = match.end()
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(content)
        section_content = content[start:end].strip()

        if len(section_content) < MIN_CHUNK_SIZE:
            continue

        sections.append({"section": heading_text, "level": heading_level, "content": section_content})

    return sections

def split_asciidoc_into_sections(content: str) -> list[dict[str, Any]]:
    sections = []
    heading_matches = list(ASCIIDOC_HEADING_PATTERN.finditer(content))

    if not heading_matches:
        sections.append({"section": "content", "level": 0, "content": content.strip()})
        return sections

    for index, match in enumerate(heading_matches):
        heading_level = len(match.group(1))
        heading_text = match.group(2).strip()
        start = match.end()
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(content)
        section_content = content[start:end].strip()

        if len(section_content) < MIN_CHUNK_SIZE:
            continue

        sections.append({"section": heading_text, "level": heading_level, "content": section_content})

    return sections

def split_plain_into_sections(content: str) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if len(p.strip()) >= MIN_CHUNK_SIZE]

    return [
        {"section": f"paragraph_{index}", "level": 0, "content": paragraph}
        for index, paragraph in enumerate(paragraphs)
    ]

def split_by_extension(content: str, extension: str) -> list[dict[str, Any]]:
    if extension == ".md":
        return split_markdown_into_sections(content)

    if extension == ".adoc":
        return split_asciidoc_into_sections(content)

    return split_plain_into_sections(content)


def split_section_into_chunks(
    section_content: str,
    max_chunk_size: int = MAX_CHUNK_SIZE,
) -> list[str]:
    if len(section_content) <= max_chunk_size:
        return [section_content]

    paragraphs = re.split(r"\n{2,}", section_content)
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if len(current_chunk) + len(paragraph) + 2 <= max_chunk_size:
            current_chunk = f"{current_chunk}\n\n{paragraph}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)

            if len(paragraph) > max_chunk_size:
                for i in range(0, len(paragraph), max_chunk_size):
                    chunks.append(paragraph[i:i + max_chunk_size])
            else:
                current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def ingest_document(
    repo_full_name: str,
    source: str,
    content: str,
    extension: str = ".md",
) -> list[dict[str, Any]]:
    sections = split_by_extension(content=content, extension=extension)

    all_chunks = []

    for section in sections:
        chunks = split_section_into_chunks(section["content"])
        chunk_total = len(chunks)

        for chunk_index, chunk_text in enumerate(chunks):
            all_chunks.append({
                "section": section["section"],
                "level": section["level"],
                "chunk_index": chunk_index,
                "chunk_total": chunk_total,
                "content": chunk_text,
            })

    stored_chunk_ids = []

    for chunk in all_chunks:
        chunk_id = store_doc_chunk(
            repo_full_name=repo_full_name,
            source=source,
            section=chunk["section"],
            chunk_index=chunk["chunk_index"],
            chunk_total=chunk["chunk_total"],
            content=chunk["content"],
            extra_metadata={
                "heading_level": chunk["level"],
                "extension": extension,
            },
        )
        stored_chunk_ids.append(chunk_id)

    return [
        {
            "chunk_id": stored_chunk_ids[i],
            "section": all_chunks[i]["section"],
            "chunk_index": all_chunks[i]["chunk_index"],
            "chunk_total": all_chunks[i]["chunk_total"],
            "content_length": len(all_chunks[i]["content"]),
        }
        for i in range(len(all_chunks))
    ]