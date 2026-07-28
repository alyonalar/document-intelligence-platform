# Architecture

Document Intelligence Platform uses a deliberately small FastAPI + SQLModel architecture for a local educational project. There is no separate frontend framework or generic repository layer; domain-oriented services own multi-table lifecycle operations.

## System Design

```mermaid
flowchart TD
    browser[Browser / Jinja2 UI] --> fastapi[FastAPI Routers]
    fastapi --> services[Service Layer]
    services --> sqlite[(SQLite / SQLModel)]
    services --> openai[Optional OpenAI]
    services --> chroma[Optional ChromaDB]
    worker[Worker] --> services
```

## Main Components

- `app/main.py`: creates the FastAPI app, mounts static assets, and registers routers.
- `app/db/models.py`: all SQLModel table definitions.
- `app/routers/`: JSON API routes and HTML/form routes.
- `app/services/`: parsing, summarization, QA, exports, jobs, OCR, vector search, and intelligence logic.
- `app/services/document_lifecycle.py`: transactional database cleanup and post-commit file cleanup.
- `app/services/intelligence_evaluation.py`: deterministic evaluation harness for the labeled regression dataset.
- `app/templates/`: Jinja2 pages.
- `app/static/`: CSS and small JavaScript for job polling.
- `app/worker.py`: queued job worker.
- `alembic/versions/`: database migrations.
- `tests/`: pytest suite.

Alembic owns the application schema. `create_all()` is used only by isolated tests and the deterministic evaluation helper, not by web application startup or demo seeding.

## Processing Pipeline

```mermaid
flowchart TD
    upload[Upload] --> validate[Validate size, extension, signature]
    validate --> store[Store file locally]
    store --> row[Create Document row]
    row --> mode{Processing mode}
    mode -->|sync| parsing[processing_status=parsing]
    mode -->|queued| job[Create ProcessingJob]
    job --> parsing
    parsing --> extract[Extract text with parser / PDF parser / OCR fallback]
    extract --> insights[Build local insights]
    insights --> classify[Classify category]
    classify --> persist[Store raw_text, summaries, keywords, dates, action_items]
    persist --> indexing[processing_status=indexing]
    indexing --> chunks[Index Chroma chunks if enabled]
    chunks --> ready[processing_status=ready]
    ready --> intelligence[Run intelligence pipeline]
```

## Intelligence Pipeline

```mermaid
flowchart TD
    raw[Document with raw_text] --> processing[intelligence_status=processing]
    processing --> entities[Extract entities]
    entities --> obligations[Extract obligations]
    obligations --> risks[Detect risks]
    risks --> relations[Build document relations]
    relations --> ready[intelligence_status=ready]
    processing --> error[intelligence_status=error]
```

Entities, obligations, risks, and relations are replaced in one database transaction. If a rule fails, the transaction rolls back and the previous consistent artifacts remain available. A separate status update records the failure.

## Data lifecycle

- SQLite foreign keys are enabled for every application connection.
- Document-owned tables use `ON DELETE CASCADE` after migration `20260717_0013`.
- The lifecycle service explicitly removes dependent rows as a compatibility measure for older local databases.
- Chroma chunks and the stored file are removed after the relational transaction commits.
- Rebuilding the workspace graph is a POST operation because it changes persisted state.

## Intelligence Model

```mermaid
flowchart TD
    document[Document] --> entities[Entities]
    entities --> relations[Relations]
    relations --> obligations[Obligations]
    obligations --> risks[Risks]
    risks --> consumers[QA / Search / Export]
```

## Notes

- The graph is stored in relational tables, not Neo4j.
- The `/graph` page is an HTML table view.
- Intelligence extraction is rule-based and designed for human review.
- Stored confidence values are rule scores, not calibrated probabilities.
- OpenAI and ChromaDB are optional.
