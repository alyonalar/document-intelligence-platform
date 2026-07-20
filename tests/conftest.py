import os
from pathlib import Path

import pytest

TEST_DB_PATH = Path("data/test_app.db")
TEST_UPLOAD_DIR = Path("data/test_uploads")

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_DIR"] = TEST_UPLOAD_DIR.as_posix()
os.environ["LLM_ENABLED"] = "false"
os.environ["SEMANTIC_SEARCH_ENABLED"] = "false"
os.environ["DEBUG"] = "false"
os.environ["ALLOWED_EXTENSIONS"] = "txt,docx,md,pdf,png,jpg,jpeg,tiff"


def pytest_sessionstart(session):
    TEST_DB_PATH.unlink(missing_ok=True)
    TEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    import app.db.models  # noqa: F401
    from app.db.engine import create_db_and_tables

    create_db_and_tables()


@pytest.fixture(autouse=True)
def isolate_database():
    """Give every test a clean database while keeping one fast SQLite schema."""
    from sqlalchemy import delete
    from sqlmodel import Session, SQLModel

    from app.db.engine import engine

    with Session(engine) as db_session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            db_session.exec(delete(table))
        db_session.commit()

    yield
