"""A small local vector store: a flat, L2-normalized numpy matrix plus a
JSON sidecar of ids/document_ids, persisted to disk under data/vectors/.

This is deliberately not an ANN index (no hnswlib/faiss): those require a
C++ build toolchain to install on Windows, which is real friction for a
personal tool that should "just work" with `pip install`. At personal
document-collection scale (thousands, not millions, of chunks) a brute
force cosine-similarity scan over the whole matrix is a few milliseconds
and is both simpler and easier to reason about than an ANN index.
"""
from __future__ import annotations

import json
import threading

import numpy as np

from app.config import settings

_lock = threading.Lock()
_ids: list[str] = []
_document_ids: list[str] = []
_vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
_loaded = False


def _ids_path():
    return settings.vector_dir / "ids.json"


def _vectors_path():
    return settings.vector_dir / "vectors.npy"


def _load_locked() -> None:
    global _ids, _document_ids, _vectors, _loaded
    if _loaded:
        return
    ids_file, vec_file = _ids_path(), _vectors_path()
    if ids_file.exists() and vec_file.exists():
        data = json.loads(ids_file.read_text(encoding="utf-8"))
        _ids = data["ids"]
        _document_ids = data["document_ids"]
        _vectors = np.load(vec_file)
    else:
        _ids, _document_ids, _vectors = [], [], np.zeros((0, 0), dtype=np.float32)
    _loaded = True


def _save_locked() -> None:
    settings.vector_dir.mkdir(parents=True, exist_ok=True)
    np.save(_vectors_path(), _vectors)
    _ids_path().write_text(json.dumps({"ids": _ids, "document_ids": _document_ids}), encoding="utf-8")


def _normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def upsert_chunks(ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
    if not ids:
        return
    global _vectors, _ids, _document_ids
    with _lock:
        _load_locked()
        new_vecs = _normalize(np.array(embeddings, dtype=np.float32))
        new_doc_ids = [m["document_id"] for m in metadatas]

        existing_index = {cid: i for i, cid in enumerate(_ids)}
        dup_positions = {existing_index[cid] for cid in ids if cid in existing_index}
        if dup_positions:
            keep = [i for i in range(len(_ids)) if i not in dup_positions]
            _vectors = _vectors[keep] if _vectors.shape[0] else _vectors
            _ids = [_ids[i] for i in keep]
            _document_ids = [_document_ids[i] for i in keep]

        _vectors = new_vecs if _vectors.shape[0] == 0 else np.vstack([_vectors, new_vecs])
        _ids.extend(ids)
        _document_ids.extend(new_doc_ids)
        _save_locked()


def delete_by_document(document_id: str) -> None:
    global _vectors, _ids, _document_ids
    with _lock:
        _load_locked()
        keep = [i for i, d in enumerate(_document_ids) if d != document_id]
        if len(keep) == len(_document_ids):
            return
        _vectors = _vectors[keep] if _vectors.shape[0] else _vectors
        _ids = [_ids[i] for i in keep]
        _document_ids = [_document_ids[i] for i in keep]
        _save_locked()


def delete_all() -> None:
    global _vectors, _ids, _document_ids, _loaded
    with _lock:
        _ids, _document_ids = [], []
        _vectors = np.zeros((0, 0), dtype=np.float32)
        _loaded = True
        _save_locked()


def query(embedding: list[float], top_k: int, where: dict | None = None) -> list[dict]:
    with _lock:
        _load_locked()
        if not _ids or _vectors.shape[0] == 0:
            return []
        allowed_doc_ids = None
        if where and "document_id" in where and "$in" in where["document_id"]:
            allowed_doc_ids = set(where["document_id"]["$in"])

        q = np.array(embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm
        sims = _vectors @ q
        order = np.argsort(-sims)

        results = []
        for idx in order:
            if allowed_doc_ids is not None and _document_ids[idx] not in allowed_doc_ids:
                continue
            results.append({"chunk_id": _ids[idx], "score": float(sims[idx])})
            if len(results) >= top_k:
                break
        return results


def count() -> int:
    with _lock:
        _load_locked()
        return len(_ids)
