# Eval results

| Config | Retrieval hit-rate | Answer correctness | Citation accuracy | Refusal accuracy (no-answer) | False-refusal rate | Injection defense rate |
|---|---|---|---|---|---|---|
| Hybrid (vector+BM25) + reranker, chunk=400 tok | 100% | 92% | 92% | 100% | 6% | 100% |
| Vector-only, no reranker, chunk=400 tok | 100% | 94% | 94% | 100% | 2% | 100% |
| Hybrid (vector+BM25) + reranker, chunk=120 tok | 100% | 96% | 98% | 100% | 2% | 100% |
