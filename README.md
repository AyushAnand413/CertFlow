# CertFlow - Bulk Certificate Generator Backend

**CertFlow** is a bulk certificate generation and verification system built with FastAPI and PostgreSQL. Organizations can submit hundreds or thousands of recipients in a single request (via REST API or CSV upload) and receive print-ready PDF certificates with embedded QR verification codes.

Instead of generating PDFs synchronously during the HTTP request or relying on external brokers like Redis/Celery, CertFlow uses PostgreSQL row-level locking (`FOR UPDATE SKIP LOCKED`) as an atomic background work queue. A single bad row never blocks the rest of a batch, and completed certificates stream directly to the user as a ZIP archive in constant memory without spiking server RAM.

## Live Deployment

- **Web Dashboard (Single & Bulk Generator):** [https://certflow-6l6x.onrender.com/dashboard/](https://certflow-6l6x.onrender.com/dashboard/)
- **Interactive API Docs (Swagger UI):** [https://certflow-6l6x.onrender.com/docs](https://certflow-6l6x.onrender.com/docs)
- **Health & DB Check:** [https://certflow-6l6x.onrender.com/health](https://certflow-6l6x.onrender.com/health)

---

## Architecture Overview

```mermaid
flowchart LR
    subgraph Clients["1. Clients"]
        Client["Web Dashboard & API Client"]
        QR["Mobile QR Scanner"]
    end

    subgraph FastAPI["2. FastAPI Server"]
        POST["POST /v1/jobs (Ingest)"]
        POLL["GET /v1/jobs/{id} (Status)"]
        DL["GET /download (ZIP Stream)"]
        VER["GET /verify/{code} (Verify)"]
    end

    subgraph Data["3. Relational Queue"]
        DB[("PostgreSQL (Jobs & Certs)")]
    end

    subgraph Workers["4. Async Worker Pool"]
        W["Worker Daemon (SKIP LOCKED)"]
        PDF["ReportLab PDF + QR Engine"]
        DISK[("PDF File Storage")]
    end

    Client -->|"1. Submit Batch"| POST
    POST -->|"Persist Rows"| DB
    Client -->|"2. Poll Progress"| POLL
    POLL -->|"Aggregate Status"| DB
    Client -->|"3. Request ZIP/PDF"| DL
    QR -->|"4. Verify Code"| VER
    VER -->|"Lookup Record"| DB

    W -->|"Claim Pending"| DB
    W -->|"Render Batch"| PDF
    PDF -->|"Write PDF"| DISK
    DISK -->|"Stream 64KB Chunks"| DL
```

---

## Design Decisions

### 1. Asynchronous Ingestion vs Synchronous Generation
* **Why:** Generating hundreds or thousands of PDFs in a single request-response cycle blocks worker threads and triggers reverse-proxy timeouts (such as HTTP 504).
* **Approach:** `POST /v1/jobs` validates the payload, writes the job and recipient rows to the database, and immediately returns `HTTP 202 Accepted` with a `job_id`. A background worker process picks up queued rows asynchronously while clients poll `GET /v1/jobs/{id}` for progress.

### 2. PostgreSQL Queue (`SKIP LOCKED`) vs External Brokers (Celery / Redis)
* **Why:** Running a separate Redis or RabbitMQ broker adds infrastructure overhead and introduces dual-write edge cases (for example, when the database commit succeeds but publishing to the broker fails).
* **Approach:** PostgreSQL acts as both the primary data store and the work queue via `SELECT ... FOR UPDATE SKIP LOCKED`:
  * **Single Atomic Transaction:** The job record and all recipient rows are committed together.
  * **Concurrent Workers:** Multiple worker processes can poll and claim batches simultaneously without locking each other out.
  * **Stale Lock Recovery:** Claimed rows get a `locked_until` lease timestamp (2 minutes). If a worker crashes mid-batch, another worker automatically reclaims expired rows once the lease times out.

### 3. ReportLab Vector PDFs vs Headless Browsers
* **Why:** Headless Chromium instances use significant memory (100MB+ per process) and are slow to spin up for large batches.
* **Approach:** PDFs are drawn directly with **ReportLab**:
  * Generates 50 to 100 certificates per second in pure Python with low memory overhead.
  * Automatically scales down font sizes when a recipient's name is unusually long so text never overflows the border.
  * Bundles TrueType Unicode fonts (`Noto Sans` and `Noto Sans Devanagari`) so non-Latin names render properly.

### 4. Streaming ZIP Downloads ($O(1)$ Memory)
* **Why:** Building a large ZIP archive in memory before sending it to the client can spike RAM usage and crash the container (`OOMKilled`).
* **Approach:** `GET /v1/jobs/{id}/download` uses `zipstream-ng` with FastAPI's `StreamingResponse` to read PDFs from disk in 64 KB chunks and stream the ZIP bytes directly to the client. Memory usage stays flat regardless of batch size.

### 5. Row-Level Validation & Failure Isolation
* **Why:** A single typo in one recipient's email address should not reject a 500-person upload or force the user to re-run the entire batch.
* **Approach:**
  * Invalid rows (such as malformed emails or blank names) are marked `rejected` during ingestion with their exact `row_index` and error reason.
  * Valid rows in the same request are queued and processed normally.
  * If a row fails during PDF rendering, only that certificate is marked `failed`, while the rest of the batch finishes (`completed_with_errors`).
  * Failed rows can be re-queued independently via `POST /v1/jobs/{id}/retry-failed`.

---

## Quickstart

### Option 1: Docker Compose

Run PostgreSQL, the FastAPI server, and the background worker:

```bash
docker compose up --build
```

Once running:
- **Web Dashboard:** http://localhost:8000/dashboard/
- **API Base URL:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **PostgreSQL:** `localhost:5432`

To stop and clean up volumes:
```bash
docker compose down -v
```

---

### Option 2: Local Python Environment

1. **Clone the repository and create a virtual environment:**
```bash
git clone https://github.com/AyushAnand413/CertFlow.git
cd CertFlow

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables (optional):**
Copy `.env.example` to `.env` or set your own values (defaults to a local SQLite database if `DATABASE_URL` is not set to Postgres):
```bash
DATABASE_URL=postgresql+psycopg2://certflow:certflow_secret@localhost:5432/certflow
STORAGE_DIR=./storage/certificates
WORKER_BATCH_SIZE=50
WORKER_LOCK_TIMEOUT_SECONDS=120
```

4. **Start the FastAPI server:**
```bash
uvicorn app.main:app --reload --port 8000
```

5. **Start the background worker in a second terminal:**
```bash
python -m app.worker.runner
```

---

## CLI Demo Script

`scripts/demo.py` runs an end-to-end walkthrough covering batch submission, partial validation errors, status polling, QR verification, and ZIP download:

```bash
python scripts/demo.py
```

If a server is running at `http://localhost:8000`, the script talks to it over HTTP; otherwise it runs against an in-process test client.

---

## API Usage & cURL Examples

### 1. Create a Bulk Generation Job
Submits a list of recipients for asynchronous certificate generation. Accepts an optional `Idempotency-Key` header to prevent duplicate jobs on network retries.

```bash
curl -X POST "http://localhost:8000/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: batch-2026-q4-drone-cert" \
  -d '{
    "certificate_info": {
      "title": "Professional Drone Pilot Certification",
      "event_name": "Autonomous Flight & Telemetry Workshop",
      "issuer_name": "Aereo Flight Academy",
      "issue_date": "2026-10-10",
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

### 2. Check Job Status & Progress
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

### 3. List Certificates in a Job
Supports filtering by status (`?status=failed` or `?status=succeeded`) and pagination.

```bash
curl "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/certificates?status=succeeded&page=1&page_size=50"
```

---

### 4. Download a Single Certificate PDF
```bash
curl -O -J "http://localhost:8000/v1/certificates/e0364d12-6d47-420c-9c90-a33408e181a0/download"
```

---

### 5. Download All Certificates as a ZIP Stream
```bash
curl -O -J "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/download"
```

---

### 6. Retry Failed Certificates
Re-queues only failed rows in the job without regenerating completed certificates.

```bash
curl -X POST "http://localhost:8000/v1/jobs/0217c390-aad4-45d6-9bf1-8c5b25596ec0/retry-failed"
```

---

### 7. Verify a Certificate Code
Returns an HTML verification badge when opened in a browser (via QR scan), or JSON when called with `Accept: application/json`.

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
  "issue_date": "2026-10-10",
  "status": "VERIFIED",
  "completed_at": "2026-10-09T12:54:28.077Z"
}
```

---

## Running Tests

Run the unit and integration test suite (`pytest`):

```bash
python -m pytest tests/ -v
```

Run with coverage:

```bash
python -m pytest tests/ --cov=app --cov-report=term-missing
```

Run the live end-to-end and security test suite:

```bash
python scripts/comprehensive_test_suite.py
```

---

## Project Structure

```text
CertFlow/
├── app/
│   ├── api/                  # FastAPI route handlers
│   │   ├── certificates.py   # Single PDF and streaming ZIP downloads
│   │   ├── deps.py           # Database session dependency
│   │   ├── jobs.py           # Job creation, listing, and status endpoints
│   │   └── verify.py         # Public QR code verification (HTML & JSON)
│   ├── config.py             # Environment settings (Pydantic)
│   ├── db/                   # Database models and session setup
│   │   ├── models.py         # SQLAlchemy Job and Certificate tables
│   │   └── session.py        # Engine and connection pool config
│   ├── main.py               # FastAPI app entrypoint
│   ├── rendering/            # PDF generation
│   │   ├── fonts/            # Bundled TrueType fonts (Noto Sans, Devanagari)
│   │   └── pdf_generator.py  # ReportLab template and QR code renderer
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # Business logic
│   │   ├── job_service.py    # Batch ingestion, validation, and idempotency
│   │   ├── progress.py       # Progress aggregation and retry logic
│   │   └── zip_stream.py     # Streaming ZIP generator
│   ├── storage/              # Local file storage adapter
│   └── worker/               # Background worker
│       ├── processor.py      # Per-certificate rendering and error capture
│       └── runner.py         # Polling loop using FOR UPDATE SKIP LOCKED
├── docker-compose.yml        # Local Postgres + API + Worker setup
├── Dockerfile                # Container build file
├── frontend/                 # Web dashboard (Single & Bulk Certificate Maker)
│   ├── index.html
│   ├── css/styles.css
│   └── js/app.js
├── requirements.txt          # Python dependencies
├── scripts/
│   ├── comprehensive_test_suite.py
│   └── demo.py
└── tests/                    # Automated test suite
    ├── test_db.py
    ├── test_downloads.py
    ├── test_jobs.py
    ├── test_rendering.py
    └── test_worker.py
```
