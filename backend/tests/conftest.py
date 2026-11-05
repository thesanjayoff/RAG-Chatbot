import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Points the vector store and any on-disk app state at a throwaway
    temp directory, and resets the in-process vectorstore/BM25 caches, so
    tests never read or write the developer's real data/ directory and
    never leak state between tests."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()

    import app.retrieval.bm25_index as bm25_index
    import app.retrieval.vectorstore as vectorstore

    vectorstore._ids = []
    vectorstore._document_ids = []
    vectorstore._vectors = np.zeros((0, 0), dtype=np.float32)
    vectorstore._loaded = True

    bm25_index._bm25 = None
    bm25_index._chunk_ids = []

    yield
