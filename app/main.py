from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers.actions import router as actions_router
from app.routers.api import router as api_router
from app.routers.collections import router as collections_router
from app.routers.documents import router as documents_router
from app.routers.history import router as history_router
from app.routers.home import router as home_router
from app.routers.intelligence import router as intelligence_router
from app.routers.intelligence_pages import router as intelligence_pages_router
from app.routers.obligations import router as obligations_router
from app.routers.risks import router as risks_router
from app.routers.workspace import router as workspace_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Document Intelligence Platform",
    description="Document intelligence platform with upload, search, QA, collections, history, RAG-ready retrieval, and exports.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


app.include_router(api_router)
app.include_router(actions_router)
app.include_router(home_router)
app.include_router(collections_router)
app.include_router(documents_router)
app.include_router(history_router)
app.include_router(intelligence_router)
app.include_router(intelligence_pages_router)
app.include_router(obligations_router)
app.include_router(risks_router)
app.include_router(workspace_router)
