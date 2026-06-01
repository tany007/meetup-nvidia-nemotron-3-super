# Maintainer Copilot

Maintainer Copilot is an AI-powered workflow assistant designed to reduce the cognitive load on open-source maintainers.

The system analyzes GitHub issues using semantic search, duplicate detection, repository context retrieval, and NVIDIA Nemotron-powered reasoning to generate structured triage recommendations. 
It helps maintainers identify duplicate issues, understand issue impact, and onboard contributors more effectively by transforming repository knowledge into actionable insights.

Developed for the NVIDIA Nemotron 3 Super Meetup Contest, Maintainer Copilot demonstrates how AI can help maintainers reduce repetitive work and focus on higher-value contributions.

---

## Problem Statement

Small open-source projects often struggle with:
- Repetitive issue triaging
- Duplicate bug reports
- Contributor onboarding

Maintainer Copilot reduces this cognitive load using semantic retrieval and NVIDIA Nemotron-powered reasoning.

## Solution Overview

Maintainer Copilot leverages semantic retrieval, vector search, and NVIDIA Nemotron-powered reasoning to help maintainers by automatically analyzing issues, identifying potential duplicates, 
and transforming repository knowledge into an intelligent onboarding assistant.

## Features

- Fetch issues, labels, and READMEs from any public GitHub repository
- AI-powered issue triage via NVIDIA Nemotron
- Semantic issue memory with ChromaDB (duplicate detection and similarity search)
- Repository documentation ingestion and RAG-based contributor Q&A
- Cache-aware analysis (avoids redundant API calls)

---

## User Interface

A lightweight browser-based dashboard. No build steps required.

### Structure

```
frontend/
├── index.html   # App shell and layout
├── style.css    # Styles
└── app.js       # API calls and DOM interactions
```

### Usage

Open `frontend/index.html` directly in a browser, or serve it with any static file server:

> Ensure the FastAPI backend is running on `http://localhost:8000` before using the dashboard.

### Dashboard Panels

| Panel | Description                                                                             |
|---|-----------------------------------------------------------------------------------------|
| **Issue Triage** | Analyze a GitHub issue by `owner/repo` and issue number                                 |
| **Analysis Hub** | Displays Nemotron triage output - type, severity, module intelligence, suggested labels |
| **Duplicate Candidates** | Lists semantically similar issues flagged as potential duplicates                       |
| **Semantic Issue Search** | Free-text search across the vector DB knowledge base                                    |
| **Onboarding Assistant** | Ask contributor questions answered from issue memory and ingested docs                  |

### API Connection Status

The header displays a live connection indicator - it pings `/health` on the load and reflects the backend status in real time.

## Architecture
![Architecture Diagram](img/Maintainer-Workflow-Intelligence-Architecture-v2.png)

## Project Structure

```text
maintainer-copilot/
├── app/
│   ├── main.py                 # FastAPI routes and API endpoints
│   ├── github_client.py        # GitHub API interactions
│   ├── nemotron_client.py      # NVIDIA Nemotron LLM integration
│   ├── vector_store.py         # Issue embeddings and semantic search (ChromaDB)
│   ├── document_store.py       # Documentation embeddings and retrieval
│   └── document_ingestion.py   # Document parsing, chunking, and indexing
│
├── chroma_db/                  # Persistent ChromaDB storage (auto-generated)
│
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## How Analysis Works

When an issue analysis request is received:

```text
POST /github/{owner}/{repo}/issues/{issue_number}/analyze
            │
            ▼
    Check ChromaDB Cache
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
 Cache Hit    Cache Miss
     │             │
     │             ├── Fetch issue details from GitHub
     │             ├── Fetch repository labels
     │             ├── Fetch README / repository context
     │             ├── Search ChromaDB for similar issues
     │             ├── Build contextual prompt
     │             ├── Invoke NVIDIA Nemotron
     │             └── Store enriched analysis in ChromaDB
     │
     ▼
Return Analysis Response
```

### Analysis Pipeline

1. Retrieve issue details and repository metadata from GitHub.
2. Search the vector database for semantically similar issues.
3. Assemble relevant context, including issue history and repository information.
4. Generate structured triage using NVIDIA Nemotron.
5. Persist the enriched result for future retrieval and duplicate detection.
6. Return the analysis response to the caller.


**Analysis output includes:**
- `issue_type` — bug / enhancement / documentation / question / maintenance
- `severity` — low / medium / high / critical
- `module_intelligence` — subsystem, component ownership, affected area
- `suggested_labels`, `duplicate_candidates`, `missing_information`
- `summary` and `reasoning`

Use `?force_refresh=true` to bypass the cache.

---

## Setup

### 1. Install dependencies
```shell
bash pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file:
```gitignore
GITHUB_TOKEN=your_github_token 
NVIDIA_API_KEY=your_nvidia_api_key 
NEMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b # optional 
NVIDIA_API_BASE_URL=https://integrate.api.nvidia.com/v1 # optional
```

### 3. Run the server
```shell
bash uvicorn app.main:app --reload
```

API docs available at `http://localhost:8000/docs`.

---

## API Reference

### General

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | API info |
| `GET` | `/health` | Health check |

### GitHub

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/github/{owner}/{repo}/issues` | List issues (`?state=open\|closed`) |
| `GET` | `/github/{owner}/{repo}/issues/{number}` | Fetch a single issue |
| `GET` | `/github/{owner}/{repo}/labels` | List repository labels |
| `GET` | `/github/{owner}/{repo}/readme` | Fetch repository README |
| `POST` | `/github/{owner}/{repo}/issues/{number}/analyze` | Analyze issue with Nemotron + vector memory |
| `POST` | `/github/{owner}/{repo}/ingest` | Ingest repository docs into vector DB |
| `GET` | `/github/{owner}/{repo}/docs/search` | Search ingested docs (`?query=`) |

### Issues

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/issues/analyze` | Analyze a raw issue (title/body) without a GitHub reference |
| `GET` | `/issues/search` | Semantic search across stored issues (`?query=`) |

### Contributors

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/contributors/ask` | Ask a question answered from issue memory + ingested docs |

---


## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| LLM | NVIDIA Nemotron |
| Vector DB | ChromaDB |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers) |
| GitHub API | PyGithub |
