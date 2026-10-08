# CertFlow — Bulk Certificate Generator Backend

CertFlow is a scalable, asynchronous backend API built to generate verified certificates in bulk for events, courses, and workshops.

## Key Features

- **Asynchronous Bulk Processing:** Ingests large batches of recipients instantly (`202 Accepted`) and processes generation via background workers.
- **PostgreSQL Queue:** Worker claiming with row-level locks (`SELECT ... FOR UPDATE SKIP LOCKED`) — reliable, durable, and crash-resilient with zero extra broker dependencies.
- **Failure Isolation & Partial Success:** An invalid recipient or rendering error never halts the rest of the batch.
- **Vector PDF Rendering:** ReportLab-powered rendering with dynamic text scaling, Unicode support, and embedded verification QR codes.
- **Constant-Memory Bulk Downloads:** Streamed ZIP archives over HTTP to prevent memory bloat and OOM crashes.
- **Idempotency Protection:** Prevents duplicate batch processing from network retries.
- **Public Verification:** Scannable QR code verification endpoint for issued certificates.

---

## Tech Stack

- **Framework:** FastAPI (Python 3.10+)
- **Database:** PostgreSQL + SQLAlchemy 2.0
- **PDF Engine:** ReportLab + QR Code
- **Containerization:** Docker Compose
