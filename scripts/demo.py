"""CertFlow End-to-End Demo Script
=================================
Demonstrates the full lifecycle of certificate generation in CertFlow:
1. Submits a batch containing diverse valid recipients (English, Hindi/Devanagari,
   ultra-long names) and deliberately invalid rows.
2. Demonstrates row-level partial success validation (HTTP 202 Accepted).
3. Polls the job status with a real-time terminal progress bar until completion.
4. Queries individual certificate records and public QR verification endpoints.
5. Streams the bulk ZIP archive to disk and validates its integrity.

Usage:
    # Run against a running CertFlow server (Docker or local uvicorn):
    python scripts/demo.py

    # Or specify custom server URL:
    python scripts/demo.py --url http://localhost:8000
"""

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict

# Ensure UTF-8 output encoding across all operating systems and shells
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx

# Sample test payload with multilingual names, long names, and deliberate errors
DEMO_PAYLOAD = {
    "certificate_info": {
        "title": "Professional Drone Pilot Certification",
        "event_name": "Autonomous Aerial Survey & Photogrammetry",
        "issuer": "Aereo Flight Academy",
        "issue_date": "October 2026",
        "description": "For demonstrated mastery of autonomous UAV flight planning, spatial telemetry, and safety regulations.",
    },
    "recipients": [
        {
            "name": "Sarah Connor",
            "email": "sarah.connor@example.com",
        },
        {
            "name": "आरव शर्मा",  # Devanagari Hindi font rendering
            "email": "aarav.sharma@example.in",
        },
        {
            "name": "Dr. Alexander Bartholomew Montgomery-Cholmondeley III",  # Dynamic font auto-scaling
            "email": "alexander.montgomery@oxford.edu",
        },
        {
            "name": "Li Wei",
            "email": "li.wei@example.cn",
        },
        {
            "name": "Priya Verma",
            "email": "priya.verma@example.com",
        },
        {
            "name": "Marcus Aurelius Vance",
            "email": "marcus.vance@example.org",
        },
        # Deliberately invalid rows to demonstrate partial ingestion
        {
            "name": "Invalid Recipient Without Email",
            "email": "not-a-valid-email-address",
        },
        {
            "name": "Another Broken Email Row",
            "email": "missing-domain@",
        },
    ]
}


def print_banner(text: str) -> None:
    print("\n" + "=" * 65)
    print(f"  {text}")
    print("=" * 65)


def render_progress_bar(succeeded: int, failed: int, total: int, width: int = 30) -> str:
    done = succeeded + failed
    fraction = done / total if total > 0 else 0
    filled = int(fraction * width)
    bar = "█" * filled + "░" * (width - filled)
    percent = int(fraction * 100)
    return f"[{bar}] {percent}% | {succeeded} succeeded, {failed} failed / {total} total"


def run_live_demo(base_url: str) -> None:
    client = httpx.Client(base_url=base_url, timeout=30.0)

    print_banner("1. SUBMITTING CERTIFICATE GENERATION JOB")
    print(f"Target Server: {base_url}")
    print(f"Total Recipients in Payload: {len(DEMO_PAYLOAD['recipients'])}")

    headers = {"Idempotency-Key": f"demo-run-{int(time.time())}"}
    resp = client.post("/v1/jobs", json=DEMO_PAYLOAD, headers=headers)

    if resp.status_code != 202:
        print(f"Error submitting job: HTTP {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    job_id = data["job_id"]
    accepted = data["accepted"]
    rejected = data["rejected"]

    print(f"✓ HTTP 202 Accepted")
    print(f"  Job ID:          {job_id}")
    print(f"  Accepted Rows:   {accepted}")
    print(f"  Rejected Rows:   {rejected}")

    if data.get("rejected_recipients"):
        print("\n  Isolated Row-Level Rejections (Partial Success):")
        for r in data["rejected_recipients"]:
            print(f"    - Row {r['row_index']} ({r['email']}): {r['error_message']}")

    print_banner("2. TRACKING WORKER PROCESSING PROGRESS")
    print("Polling job status...")

    while True:
        status_resp = client.get(f"/v1/jobs/{job_id}")
        if status_resp.status_code != 200:
            print(f"Error polling status: HTTP {status_resp.status_code}")
            break

        status_data = status_resp.json()
        status = status_data["status"]
        progress = status_data["progress"]
        total = progress["total"]
        succeeded = progress["succeeded"]
        failed = progress["failed"]

        bar = render_progress_bar(succeeded, failed, total)
        sys.stdout.write(f"\r  Status: {status.upper():<20} | {bar}")
        sys.stdout.flush()

        if status in ("completed", "completed_with_errors", "failed"):
            print()
            break
        time.sleep(0.6)

    print_banner("3. RETRIEVING GENERATED CERTIFICATES")
    certs_resp = client.get(f"/v1/jobs/{job_id}/certificates")
    first_cert = None
    if certs_resp.status_code == 200:
        certs_data = certs_resp.json()
        items = certs_data.get("items", [])
        print(f"Total Certificates Recorded: {certs_data.get('total', len(items))}")
        for i, c in enumerate(items[:4], 1):
            if c["status"] == "succeeded" and not first_cert:
                first_cert = c
            print(f"  [{i}] {c['recipient_name']} <{c['recipient_email']}>")
            print(f"      Status: {c['status']} | Code: {c['verification_code']}")
            if c.get("download_url"):
                print(f"      PDF: {base_url}{c['download_url']}")

        if len(items) > 4:
            print(f"  ... and {len(items) - 4} more")

    if first_cert:
        print_banner("4. TESTING PUBLIC QR VERIFICATION ENDPOINT")
        verify_code = first_cert["verification_code"]
        print(f"Verifying code: {verify_code}")
        v_resp = client.get(f"/verify/{verify_code}", headers={"Accept": "application/json"})
        if v_resp.status_code == 200:
            v_data = v_resp.json()
            print("✓ Public Verification Response (JSON):")
            print(json.dumps(v_data, indent=2, ensure_ascii=False))
        else:
            print(f"Verification query failed: HTTP {v_resp.status_code}")

    print_banner("5. STREAMING BULK ZIP DOWNLOAD")
    zip_url = f"/v1/jobs/{job_id}/download"
    print(f"Downloading stream from {base_url}{zip_url}...")

    out_filename = "demo_certificates.zip"
    start_time = time.time()
    with client.stream("GET", zip_url) as stream_resp:
        if stream_resp.status_code == 200:
            with open(out_filename, "wb") as f:
                for chunk in stream_resp.iter_bytes():
                    f.write(chunk)
            elapsed = time.time() - start_time
            size_kb = os.path.getsize(out_filename) / 1024
            print(f"✓ Download complete: {out_filename} ({size_kb:.1f} KB in {elapsed:.2f}s)")

            # Verify ZIP contents
            with zipfile.ZipFile(out_filename, "r") as zf:
                files = zf.namelist()
                print(f"✓ ZIP Archive verified. Contains {len(files)} files:")
                for name in files:
                    info = zf.getinfo(name)
                    print(f"    - {name} ({info.file_size / 1024:.1f} KB)")
        else:
            print(f"ZIP download returned HTTP {stream_resp.status_code}")

    print_banner("DEMO COMPLETED SUCCESSFULLY!")


def run_standalone_demo() -> None:
    """Runs the demo in-process using FastAPI TestClient & direct worker runner."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api.deps import get_db
    from app.db.models import Base
    from app.main import app
    from app.worker.runner import claim_next_batch
    from app.worker.processor import process_batch
    from app.storage import get_storage

    print_banner("Running Self-Contained In-Memory Demo (No External Server)")

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    print("\n1. Submitting batch to in-process app...")
    resp = client.post("/v1/jobs", json=DEMO_PAYLOAD, headers={"Idempotency-Key": f"demo-{int(time.time())}"})
    data = resp.json()
    job_id = data["job_id"]
    print(f"✓ Job created: {job_id} (Accepted: {data['accepted']}, Rejected: {data['rejected']})")
    for r in data["rejected_recipients"]:
        print(f"  - Row {r['row_index']} ({r['email']}): {r['error_message']}")

    print("\n2. Executing background worker process...")
    storage = get_storage()
    worker_db = TestingSession()
    claimed = claim_next_batch(worker_db, batch_size=50)
    if claimed:
        stats = process_batch(worker_db, claimed, storage=storage)
        print(f"✓ Worker processed {len(claimed)} certificates ({stats['succeeded']} succeeded, {stats['failed']} failed).")
    worker_db.close()

    print("\n3. Checking Job Status...")
    status_resp = client.get(f"/v1/jobs/{job_id}").json()
    print(f"  Final Status: {status_resp['status']}")
    prog = status_resp["progress"]
    print(f"  Progress: {prog['succeeded']} succeeded, {prog['failed']} failed, {prog['rejected']} rejected / {prog['total']} total")

    print("\n4. Verifying Public Verification...")
    certs_resp = client.get(f"/v1/jobs/{job_id}/certificates").json()
    first_cert = next(c for c in certs_resp["items"] if c["status"] == "succeeded")
    verify_resp = client.get(f"/verify/{first_cert['verification_code']}", headers={"Accept": "application/json"}).json()
    print(f"✓ Certificate Verified: {verify_resp['recipient_name']} - {verify_resp.get('event_name', '')}")
    print(f"  Verification Code: {verify_resp['verification_code']}")

    print("\n5. Testing Streaming Bulk ZIP...")
    zip_resp = client.get(f"/v1/jobs/{job_id}/download")
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        print(f"✓ Streamed ZIP received: {len(zf.namelist())} PDF files packaged.")
        for name in zf.namelist():
            print(f"    - {name}")

    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)

    print_banner("STANDALONE DEMO COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CertFlow Demo Runner")
    parser.add_argument("--url", default="http://localhost:8000", help="CertFlow Base URL")
    args = parser.parse_args()

    # Detect if live server is running
    is_live = False
    try:
        check = httpx.get(f"{args.url}/health", timeout=1.5)
        if check.status_code == 200:
            is_live = True
    except Exception:
        is_live = False

    if is_live:
        run_live_demo(args.url)
    else:
        print(f"Note: CertFlow server not detected at {args.url}.")
        print("Running self-contained in-memory execution...")
        run_standalone_demo()
