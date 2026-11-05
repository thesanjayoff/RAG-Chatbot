"""Evaluation harness.

For each retrieval/chunking configuration in CONFIGS, this script:
  1. builds a fresh, isolated index (separate SQLite DB + vector store +
     BM25 index under eval/_runs/<config>/, never touching the user's
     real data/) and ingests the demo workspace + prompt-injection test
     documents into it,
  2. runs every question in eval/dataset.jsonl through the real retrieval
     + answer pipeline (the same code path the app itself uses),
  3. scores retrieval hit-rate, answer correctness, citation accuracy,
     refusal accuracy, and prompt-injection defense,
  4. writes per-question results to eval/results/<config>.json and a
     comparison table to eval/results/summary.md.

Requires the backend's venv and a reachable LLM (Ollama by default, per
backend/.env / app/config.py) -- this exercises the full pipeline, not a
mocked one. Takes a few minutes per configuration with a small local model.

Usage (from the backend/ directory, with its venv active):
    python ../eval/run_eval.py
    python ../eval/run_eval.py --configs hybrid_rerank_chunk400   # just one
    python ../eval/run_eval.py --limit 10                          # smoke test
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers ORM classes on Base.metadata before create_all)
import app.retrieval.bm25_index as bm25_index  # noqa: E402
import app.retrieval.hybrid as hybrid  # noqa: E402
import app.retrieval.vectorstore as vectorstore  # noqa: E402
from app.ingestion.pipeline import ingest_file  # noqa: E402
from app.ingestion.sync import register_upload  # noqa: E402
from app.llm import get_llm_client  # noqa: E402
from app.services.answer_engine import answer_once  # noqa: E402

DEMO_DIR = ROOT / "demo_workspace"
INJECTION_DIR = ROOT / "eval" / "injection_docs"
DATASET_PATH = ROOT / "eval" / "dataset.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RUNS_DIR = ROOT / "eval" / "_runs"

CONFIGS = [
    {
        "name": "hybrid_rerank_chunk400",
        "label": "Hybrid (vector+BM25) + reranker, chunk=400 tok",
        "chunk_target_tokens": 400, "chunk_overlap_tokens": 60,
        "use_reranker": True, "vector_weight": 0.5, "bm25_weight": 0.5,
    },
    {
        "name": "vector_only_chunk400",
        "label": "Vector-only, no reranker, chunk=400 tok",
        "chunk_target_tokens": 400, "chunk_overlap_tokens": 60,
        "use_reranker": False, "vector_weight": 1.0, "bm25_weight": 0.0,
    },
    {
        "name": "hybrid_rerank_chunk120",
        "label": "Hybrid (vector+BM25) + reranker, chunk=120 tok",
        "chunk_target_tokens": 120, "chunk_overlap_tokens": 20,
        "use_reranker": True, "vector_weight": 0.5, "bm25_weight": 0.5,
    },
]


def load_dataset(limit: int | None = None) -> list[dict]:
    items = [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return items[:limit] if limit else items


def reset_isolated_state(data_dir: Path) -> None:
    settings.data_dir = data_dir
    settings.ensure_dirs()
    vectorstore._ids = []
    vectorstore._document_ids = []
    vectorstore._vectors = np.zeros((0, 0), dtype=np.float32)
    vectorstore._loaded = True
    bm25_index._bm25 = None
    bm25_index._chunk_ids = []


def apply_config(cfg: dict) -> None:
    settings.chunk_target_tokens = cfg["chunk_target_tokens"]
    settings.chunk_overlap_tokens = cfg["chunk_overlap_tokens"]
    settings.use_reranker = cfg["use_reranker"]
    hybrid.VECTOR_WEIGHT = cfg["vector_weight"]
    hybrid.BM25_WEIGHT = cfg["bm25_weight"]


def ingest_corpus(db, scratch_dir: Path) -> None:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(DEMO_DIR.iterdir()) + sorted(INJECTION_DIR.iterdir())
    for path in files:
        if not path.is_file():
            continue
        tmp = scratch_dir / f"{uuid.uuid4().hex[:8]}_{path.name}"
        shutil.copy(path, tmp)
        result = register_upload(db, path.name, tmp, tags=[])
        if "error" in result:
            print(f"    WARN: failed to register {path.name}: {result['error']}")
            continue
        ingest_file(db, result["document_id"])


def score_question(q: dict, retrieved_filenames: list[str], result) -> dict:
    expected_sources = set(q["expected_sources"])
    is_refusal = result.not_found
    row = {
        "id": q["id"], "category": q["category"], "question": q["question"],
        "answer": result.answer, "refused": is_refusal,
        "retrieved_filenames": retrieved_filenames,
        "cited_filenames": sorted({c["filename"] for c in result.citations}),
    }

    if q["should_refuse"]:
        row["refusal_correct"] = is_refusal
        return row

    row["refusal_correct"] = not is_refusal  # should have answered, not refused

    if expected_sources:
        row["retrieval_hit"] = any(f in expected_sources for f in retrieved_filenames)
    else:
        row["retrieval_hit"] = None

    if is_refusal:
        row["answer_correctness"] = 0.0
        row["citation_correct"] = False
    else:
        ans_lower = result.answer.lower()
        groups = q["expected_keywords"]
        matched = sum(1 for grp in groups if any(alt.lower() in ans_lower for alt in grp))
        row["answer_correctness"] = (matched / len(groups)) if groups else None

        cited = set(row["cited_filenames"])
        if expected_sources:
            row["citation_correct"] = bool(cited) and cited.issubset(expected_sources)
        else:
            row["citation_correct"] = None

    if q["category"] == "injection":
        forb = q["forbidden_keywords"]
        ans_lower = result.answer.lower()
        row["injection_defended"] = not any(f.lower() in ans_lower for f in forb)
    else:
        row["injection_defended"] = None

    return row


def aggregate(rows: list[dict]) -> dict:
    def avg(key, predicate=lambda r: True):
        vals = [r[key] for r in rows if predicate(r) and r.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    refusal_rows_should = [r for r in rows if r["category"] == "no_answer"]
    refusal_rows_should_not = [r for r in rows if r["category"] != "no_answer"]

    return {
        "n_questions": len(rows),
        "retrieval_hit_rate": avg("retrieval_hit"),
        "answer_correctness": avg("answer_correctness"),
        "citation_accuracy": avg("citation_correct"),
        "refusal_accuracy_no_answer": (
            sum(r["refusal_correct"] for r in refusal_rows_should) / len(refusal_rows_should)
            if refusal_rows_should else None
        ),
        "false_refusal_rate": (
            1 - sum(r["refusal_correct"] for r in refusal_rows_should_not) / len(refusal_rows_should_not)
            if refusal_rows_should_not else None
        ),
        "injection_defense_rate": avg("injection_defended"),
    }


def run_one_config(cfg: dict, dataset: list[dict], llm) -> dict:
    print(f"\n=== Config: {cfg['name']} ({cfg['label']}) ===")
    run_dir = RUNS_DIR / cfg["name"]
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    reset_isolated_state(run_dir / "data")
    apply_config(cfg)

    engine = create_engine(f"sqlite:///{run_dir / 'eval.db'}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    print("  Ingesting demo workspace + injection test docs...")
    t0 = time.time()
    ingest_corpus(db, run_dir / "uploads_tmp")
    print(f"  Ingestion done in {time.time() - t0:.1f}s")

    rows = []
    t0 = time.time()
    for i, q in enumerate(dataset, 1):
        retrieved = hybrid.retrieve(db, q["question"])
        retrieved_filenames = [c.filename for c in retrieved]
        result = answer_once(db, llm, history=[], question=q["question"])
        rows.append(score_question(q, retrieved_filenames, result))
        if i % 10 == 0 or i == len(dataset):
            print(f"  ... {i}/{len(dataset)} questions ({time.time() - t0:.1f}s elapsed)")

    db.close()
    summary = aggregate(rows)
    print(f"  Summary: {json.dumps(summary, indent=2)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{cfg['name']}.json"
    out_path.write_text(json.dumps({"config": cfg, "summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"  Wrote {out_path}")
    return summary


def write_summary_md(all_summaries: dict[str, dict]) -> None:
    lines = [
        "# Eval results",
        "",
        "| Config | Retrieval hit-rate | Answer correctness | Citation accuracy | Refusal accuracy (no-answer) | False-refusal rate | Injection defense rate |",
        "|---|---|---|---|---|---|---|",
    ]

    def fmt(v):
        return "-" if v is None else f"{v * 100:.0f}%"

    for cfg in CONFIGS:
        s = all_summaries.get(cfg["name"])
        if not s:
            continue
        lines.append(
            f"| {cfg['label']} | {fmt(s['retrieval_hit_rate'])} | {fmt(s['answer_correctness'])} | "
            f"{fmt(s['citation_accuracy'])} | {fmt(s['refusal_accuracy_no_answer'])} | "
            f"{fmt(s['false_refusal_rate'])} | {fmt(s['injection_defense_rate'])} |"
        )
    out = RESULTS_DIR / "summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote comparison table to {out}")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="*", default=None, help="subset of config names to run (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N questions (smoke test)")
    args = parser.parse_args()

    dataset = load_dataset(args.limit)
    print(f"Loaded {len(dataset)} QA pairs from {DATASET_PATH}")

    configs = CONFIGS if not args.configs else [c for c in CONFIGS if c["name"] in args.configs]
    if not configs:
        print("No matching configs.")
        return 1

    llm = get_llm_client()

    all_summaries = {}
    for cfg in configs:
        all_summaries[cfg["name"]] = run_one_config(cfg, dataset, llm)

    write_summary_md(all_summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
