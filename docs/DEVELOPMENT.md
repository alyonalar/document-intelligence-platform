# Development Guide

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
alembic upgrade head
python -m app.seed_demo
uvicorn app.main:app --reload
```

## Helper Script

```powershell
.\scripts\dev.ps1 install
.\scripts\dev.ps1 migrate
.\scripts\dev.ps1 seed
.\scripts\dev.ps1 run
.\scripts\dev.ps1 worker
.\scripts\dev.ps1 test
```

Set `DOCUMENT_ASSISTANT_PYTHON` if Python is not on `PATH`.

## Configuration

Configuration is loaded from environment variables and `.env`.

```env
APP_NAME=Document Intelligence Platform
DEBUG=false
APP_PORT=8000
DATABASE_URL=sqlite:///data/app.db
UPLOAD_DIR=data/uploads
MAX_FILE_SIZE_MB=20
ALLOWED_EXTENSIONS=txt,docx,md,pdf,png,jpg,jpeg,tiff

LLM_ENABLED=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
SEMANTIC_SEARCH_ENABLED=false
CHROMA_DIR=data/chroma

OCR_ENABLED=false
OCR_ENGINE=tesseract
OCR_LANGUAGE=eng+rus
TESSERACT_CMD=tesseract
OCR_DPI=200
OCR_MAX_PAGES=5
OCR_PREPROCESS_IMAGES=true
OCR_IMAGE_TARGET_WIDTH=1800
OCR_CONTRAST_FACTOR=1.6

PROCESSING_MODE=sync
PROCESSING_MAX_ATTEMPTS=3
PROCESSING_STALE_MINUTES=30
```

## Docker Port Conflicts

For Docker port conflicts, override the host port before running Compose:

```powershell
$env:APP_PORT=8001
docker compose up --build
```

Then open `http://127.0.0.1:8001`.

Run tests:

```powershell
pytest
```

Quality checks and the deterministic intelligence evaluation:

```powershell
ruff check app tests alembic scripts
ruff format --check app tests alembic scripts
python -m scripts.evaluate_intelligence
```

CI is defined in `.github/workflows/ci.yml` and runs on `push` and `pull_request` with Python 3.12. It applies migrations to an empty database, runs Ruff and coverage-enabled tests, builds the Docker image, and smoke-tests `/health`.

## OCR

OCR is optional. It requires Python packages plus system Tesseract and Poppler.

Windows example:

```powershell
winget install UB-Mannheim.TesseractOCR
winget install oschwartz10612.Poppler
```

## Semantic Search

Semantic search is optional and disabled by default. Add `OPENAI_API_KEY` first, then enable semantic search from `Administrative tools` on the home page. The runtime switch is stored in `data/runtime_settings.json`.

When disabled or misconfigured, the app continues with local keyword behavior.
