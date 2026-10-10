# CertFlow — Bulk Certificate Generator Backend

CertFlow is a high-throughput, asynchronous backend system designed to generate, deliver, and verify tamper-proof PDF certificates in bulk for educational programs, aerial photogrammetry workshops, and corporate training events.

Built for resilience, CertFlow processes large batches of recipients without blocking HTTP clients, provides row-level failure isolation, streams multi-gigabyte ZIP archives in constant memory ($O(1)$ RAM), and guarantees crash recovery without requiring heavy broker dependencies like Celery or Redis.

---

## Architecture Overview

```mermaid
flowchart TD
    Client["Client / Web Dashboard"] -->|"1. POST /v1/jobs (Idempotent)"| API["FastAPI API Server"]
    API -->|"2. Ingest & Validate Rows"| DB[("PostgreSQL Database")]
    API -->|"3. HTTP 202 Accepted"| Client

    subgraph BackgroundProcessing["Background Processing"]
        Worker["Worker Runner Daemon"] -->|"4. SELECT ... FOR UPDATE SKIP LOCKED"| DB
        Worker -->|"5. Render Vector PDF + QR Code"| Engine["ReportLab Engine"]
        Engine -->|"6. Save PDF (Local / Cloud)"| Storage["Storage Provider"]
        Worker -->|"7. Update Status (Succeeded / Failed)"| DB
    end

    Client -->|"8. Poll GET /v1/jobs/{id}"| API
    Client -->|"9. GET /v1/jobs/{id}/download"| API
    API -->|"10. Stream Chunks O(1) Memory"| Client
    
    Verifier["Mobile / Browser Scanner"] -->|"11. Scan QR -> GET /verify/{code}"| API
    API -->|"12. Render Verification Card / JSON"| Verifier
```

---

## Architectural & Technical Decisions

### 1. Asynchronous Ingestion vs Synchronous Generation
* **The Problem:** Rendering a batch of 1,000+ vector certificates takes several seconds or minutes. Holding an HTTP connection open causes client timeouts, reverse proxy drops (e.g., Nginx 504 Gateway Timeout), and exhausts server thread pools.
* **CertFlow Solution:** The ingestion endpoint (`POST /v1/jobs`) validates recipient schemas immediately, persists rows in the database, and returns `HTTP 202 Accepted` in milliseconds with a trackable `job_id`. Background workers consume and process items asynchronously.

### 2. PostgreSQL Queue with `SKIP LOCKED` vs External Brokers (Celery / Redis)
* **The Problem:** Adding Celery, Redis, or RabbitMQ introduces operational complexity, dual-write consistency hazards (database transaction succeeds but broker publish fails, or vice-versa), and additional infrastructure failure points.
* **CertFlow Solution:** PostgreSQL serves as a high-throughput, transactional queue using `SELECT ... FOR UPDATE SKIP LOCKED`.
  * **Zero Dual-Write Risk:** Jobs and recipient tasks are committed together in a single atomic database transaction.
  * **Row-Level Concurrency:** Multiple worker processes claim independent batches concurrently without lock contention.
  * **Automatic Crash Recovery:** Each claimed row receives a lease timestamp (`locked_until = now() + 2 minutes`). If a worker container crashes or is abruptly killed (`SIGKILL`), expired leases are automatically re-claimed by surviving workers.

### 3. ReportLab Vector Engine vs Headless Chromium (Puppeteer / Playwright)
* **The Problem:** Headless browsers consume ~100MB+ RAM per process, have high startup latency, and can easily crash the container under bulk workloads of 5,000 certificates.
* **CertFlow Solution:** Pure-Python vector graphics rendering with **ReportLab**:
  * Consistently renders at **50–100 certificates per second** with negligible memory usage.
  * Vector-sharp typography and vector borders at any zoom level.
  * Dynamic font auto-scaling to prevent long recipient names from overflowing.
  * TrueType Unicode support (bundled with Noto Sans for Latin and Noto Sans Devanagari for Hindi).

### 4. Constant-Memory Streaming Bulk ZIP ($O(1)$ RAM)
* **The Problem:** Compressing 10,000 PDF certificates into a ZIP file in memory can consume gigabytes of RAM, triggering Linux Out-Of-Memory (`OOMKilled`) termination.
* **CertFlow Solution:** Implemented generator-based chunk streaming via `zipstream-ng`. The API reads certificate PDFs from storage in 64 KB chunks and streams the compressed ZIP stream directly to the HTTP response (`StreamingResponse`). The server's memory footprint remains constant regardless of whether the archive contains 10 or 10,000 certificates.

### 5. Partial Success & Row-Level Failure Isolation
* **The Problem:** In bulk ingestion, rejecting an entire batch because 1 out of 500 email addresses has a typo ruins user experience and causes unnecessary re-uploads.
* **CertFlow Solution:**
  * Syntactically invalid recipients are marked as `rejected` upfront with exact row indices and diagnostic reasons.
  * Valid recipients are immediately queued and processed.
  * If a specific certificate encounters a rendering error during processing, only that row is marked `failed` with error details; all other 499 certificates succeed and the job transitions to `completed_with_errors`.
  * A dedicated `POST /v1/jobs/{id}/retry-failed` endpoint allows retrying only the failed subset without re-generating succeeded certificates.

---

## Quickstart Guide

### Option 1: Running with Docker Compose (Recommended)

Start PostgreSQL, the FastAPI API server, and the background worker daemon in isolated containers:

```bash
docker compose up --build
```

The services will start:
- **Online Certificate Maker UI (Dashboard):** http://localhost:8000/dashboard/
- **API Server:** http://localhost:8000
- **Interactive Swagger Docs:** http://localhost:8000/docs
- **PostgreSQL Database:** `localhost:5432`

To shut down:
```bash
docker compose down -v
```

---

### Option 2: Running Locally with Virtual Environment

1. **Clone the repository and create virtual environment:**
```bash
git clone https://github.com/AyushAnand413/CertFlow.git
cd CertFlow

python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables (optional, defaults provided):**
Create a `.env` file or export variables:
```bash
DATABASE_URL=postgresql+psycopg2://certflow:certflow_secret@localhost:5432/certflow
STORAGE_DIR=./storage/certificates
WORKER_BATCH_SIZE=50
WORKER_LOCK_TIMEOUT_SECONDS=120
```

4. **Start the API server:**
```bash
uvicorn app.main:app --reload --port 8000
```

5. **Start the background worker in a separate terminal:**
```bash
python -m app.worker.runner
```

---

## End-to-End Demo Script

CertFlow includes a complete demo script in `scripts/demo.py` that demonstrates batch ingestion, partial failure isolation, terminal progress polling, public verification, and bulk ZIP streaming.

```bash
python scripts/demo.py
```

*Note: If the live server is running at `http://localhost:8000`, the script automatically connects to it over HTTP. If no server is running, the script seamlessly executes a self-contained in-memory run using FastAPI's test engine.*

---

## API Reference & cURL Examples

### 1. Ingest Bulk Generation Job
Accepts a batch of recipients and starts asynchronous generation. Supports idempotency keys to prevent duplicate billing or processing.

```bash
curl -X POST "http://localhost:8000/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: batch-2026-q4-drone-cert" \
  -d '{
    "certificate_info": {
      "title": "Professional Drone Pilot Certification",
      "event_name": "Autonomous Flight & Telemetry Workshop",
      "issuer": "Aereo Flight Academy",
      "issue_date": "October 2026",
      "description": "Completed advanced flight simulations and spatial photogrammetry."
    },
    "recipients": [
      {"name": "Sarah Connor", "email": "sarah.connor@example.com"},
      {"name": "आरव शर्मा", "email": "aarav.sharma@example.in"},
      {"name": "Dr. Alexander Montgomery", "email": "alex.m@oxford.edu"},
      {"name": "Invalid Recipient", "email": "broken-email-format"}
    ]
  }'
```

**Response (`HTTP 202 Accepted`):**
```json
{
  "job_id": "0217c390-aad4-45d6-9bf1-8c5b25596ec0",
  "status": "queued",
  "total": 4,
  "accepted": 3,
  "rejected": 1,
  "status_url": "/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0",
  "created_at": "2026-10-09T12:54:28.000Z",
  "rejected_recipients": [
    {
      "row_index": 3,
      "name": "Invalid Recipient",
      "email": "broken-email-format",
      "status": "rejected",
      "error_code": "VALIDATION_ERROR",
      "error_message": "Invalid email format: 'broken-email-format'"
    }
  ]
}
```

---

### 2. Poll Job Status & Progress
```bash
curl "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0"
```

**Response (`HTTP 200 OK`):**
```json
{
  "job_id": "0217c390-aad4-45d6-9bf1-8c5b25596ec0",
  "status": "completed_with_errors",
  "certificate_info": {
    "title": "Professional Drone Pilot Certification",
    "event_name": "Autonomous Flight & Telemetry Workshop"
  },
  "progress": {
    "total": 4,
    "pending": 0,
    "processing": 0,
    "succeeded": 3,
    "failed": 0,
    "rejected": 1,
    "percent_complete": 100.0
  },
  "download_url": "/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/download",
  "created_at": "2026-10-09T12:54:28.000Z",
  "started_at": "2026-10-09T12:54:28.014Z",
  "finished_at": "2026-10-09T12:54:28.214Z"
}
```

---

### 3. List Certificates for a Job
Supports filtering by status (e.g. `?status=failed` or `?status=succeeded`) and pagination.

```bash
curl "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/certificates?status=succeeded&page=1&page_size=50"
```

---

### 4. Download Single Certificate PDF
```bash
curl -O -J "http://localhost:8000/v1/certificates/e0364d12-6d47-420c-9c90-a33408e181a0/download"
```

---

### 5. Stream Bulk Certificates (Constant-Memory ZIP)
```bash
curl -O -J "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/download"
```

---

### 6. Retry Failed Certificates
Re-queues only failed items for worker generation without touching succeeded records.

```bash
curl -X POST "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/retry-failed"
```

---

### 7. Public QR Verification Endpoint
Accessible via mobile QR scan (returns HTML card) or HTTP client with `Accept: application/json`.

```bash
curl -H "Accept: application/json" "http://localhost:8000/verify/CERT-EE34488B"
```

**Response (`HTTP 200 OK`):**
```json
{
  "valid": true,
  "verification_code": "CERT-EE34488B",
  "recipient_name": "Sarah Connor",
  "event_name": "Autonomous Aerial Survey & Photogrammetry",
  "issuer": "Aereo Flight Academy",
  "issue_date": "October 2026",
  "status": "succeeded",
  "completed_at": "2026-10-09T12:54:28.077Z"
}
```

---

## Running Automated Tests

CertFlow includes a test suite covering database queries, row locking, PDF rendering with TrueType fonts, worker claiming & recovery, API endpoints, partial success handling, and streaming downloads.

To run the complete test suite:

```bash
python -m pytest tests/ -v
```

To run with test coverage reporting:

```bash
python -m pytest tests/ --cov=app --cov-report=term-missing
```

---

## Directory Structure

```text
CertFlow/
├── app/
│   ├── api/                  # FastAPI route controllers
│   │   ├── certificates.py   # PDF download and bulk streaming endpoints
│   │   ├── deps.py           # Dependency injection (DB session)
│   │   ├── jobs.py           # Job submission and status polling
│   │   └── verify.py         # Public QR verification (HTML & JSON)
│   ├── config.py             # Pydantic environment configuration
│   ├── db/                   # Database layer
│   │   ├── models.py         # SQLAlchemy Job and Certificate models
│   │   └── session.py        # Connection pooling and engine setup
│   ├── main.py               # FastAPI application entrypoint
│   ├── rendering/            # PDF generation engine
│   │   ├── fonts/            # Bundled TrueType Unicode fonts (Noto Sans, Devanagari)
│   │   └── template.py       # ReportLab canvas drawing & QR generator
│   ├── schemas/              # Pydantic request/response models
│   │   ├── certificate.py
│   │   ├── job.py
│   │   └── recipient.py
│   ├── services/             # Core business logic
│   │   ├── job_service.py    # Batch ingestion and idempotency handling
│   │   ├── progress.py       # Status calculation and failed retries
│   │   └── zip_stream.py     # Constant-memory streaming ZIP builder
│   ├── storage/              # Pluggable storage abstraction
│   │   ├── base.py
│   │   └── local.py
│   └── worker/               # Background task queue & worker
│       ├── processor.py      # Individual certificate rendering & row failure isolation
│       └── runner.py         # Atomic SELECT ... FOR UPDATE SKIP LOCKED daemon
├── docker-compose.yml        # Multi-container orchestration (Postgres, API, Worker)
├── Dockerfile                # Production container definition
├── frontend/                 # Interactive Client-Side Certificate Maker UI
│   ├── index.html            # Single & Bulk Certificate Maker studio
│   ├── css/styles.css        # Light-theme styling & live certificate canvas
│   └── js/app.js             # Live preview, CSV validator, progress polling
├── requirements.txt          # Python dependencies
├── scripts/
│   ├── comprehensive_test_suite.py # 5-phase live E2E & security stress suite
│   └── demo.py               # End-to-end interactive CLI demonstration
└── tests/                    # Unit and integration test suite
    ├── test_db.py
    ├── test_downloads.py
    ├── test_jobs.py
    ├── test_rendering.py
    └── test_worker.py
```

---

## License

This project was developed for the Aereo Bulk Certificate Generator assignment. All rights reserved.
