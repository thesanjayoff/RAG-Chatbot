"""Upload the demo workspace (and optionally the injection test docs) into
a running instance of the app, so a new user has something to try
immediately. Run the backend first (`python run.py`), then:

    python scripts/seed_demo.py                 # demo docs only
    python scripts/seed_demo.py --with-injection-tests
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo_workspace"
INJECTION_DIR = ROOT / "eval" / "injection_docs"
BASE_URL = "http://127.0.0.1:8731"


def upload(client: httpx.Client, path: Path, tags: str) -> str | None:
    with path.open("rb") as f:
        resp = client.post(
            "/api/documents/upload",
            files={"file": (path.name, f)},
            data={"tags": tags},
            timeout=120,
        )
    if resp.status_code != 200:
        print(f"  FAILED  {path.name}: {resp.status_code} {resp.text}")
        return None
    body = resp.json()
    if body.get("status") == "duplicate":
        print(f"  skip    {path.name} (already indexed)")
        return None
    print(f"  queued  {path.name}")
    return body.get("document_id")


def wait_for_completion(client: httpx.Client, document_ids: list[str], timeout_s: int = 180) -> None:
    deadline = time.time() + timeout_s
    pending = set(document_ids)
    while pending and time.time() < deadline:
        time.sleep(2)
        for doc_id in list(pending):
            resp = client.get(f"/api/documents/{doc_id}")
            if resp.status_code != 200:
                pending.discard(doc_id)
                continue
            doc = resp.json()
            if doc["status"] in ("ready", "error"):
                flag = "OK" if doc["status"] == "ready" else f"ERROR: {doc['error_message']}"
                print(f"  {doc['filename']}: {flag}")
                pending.discard(doc_id)
    if pending:
        print(f"  {len(pending)} document(s) still processing after {timeout_s}s (check the Library tab)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-injection-tests", action="store_true", help="also upload the 3 prompt-injection eval documents")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    try:
        with httpx.Client(base_url=args.base_url) as client:
            client.get("/api/documents", timeout=5)
    except httpx.ConnectError:
        print(f"Could not reach {args.base_url} -- start the backend first (python run.py)")
        return 1

    with httpx.Client(base_url=args.base_url) as client:
        print(f"Uploading demo workspace from {DEMO_DIR} ...")
        doc_ids = []
        for path in sorted(DEMO_DIR.iterdir()):
            if path.is_file():
                doc_id = upload(client, path, tags="demo,northwind")
                if doc_id:
                    doc_ids.append(doc_id)

        if args.with_injection_tests:
            print(f"\nUploading prompt-injection eval docs from {INJECTION_DIR} ...")
            for path in sorted(INJECTION_DIR.iterdir()):
                if path.is_file():
                    doc_id = upload(client, path, tags="eval,injection-test")
                    if doc_id:
                        doc_ids.append(doc_id)

        if doc_ids:
            print(f"\nWaiting for {len(doc_ids)} document(s) to finish indexing ...")
            wait_for_completion(client, doc_ids)

    print("\nDone. Open the app and try: \"What is the Falcon 3's battery life?\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
