import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_STORAGE", "1")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "storage"))
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    os.environ.pop("LOCAL_STORAGE", None)
    os.environ.pop("LOCAL_STORAGE_DIR", None)
