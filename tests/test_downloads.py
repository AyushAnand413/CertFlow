import io
import uuid
import zipfile
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.models import Base, Job, Certificate, CertificateStatus, JobStatus
from app.main import app
from app.rendering.template import render_certificate
from app.storage import get_storage
from app.storage.local import LocalStorage


@pytest.fixture
def client_env(tmp_path):
    """Provides a TestClient, in-memory DB, and temporary storage override."""
    test_storage = LocalStorage(str(tmp_path))
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
    app.dependency_overrides[get_storage] = lambda: test_storage

    with TestClient(app) as client:
        yield client, TestingSession, test_storage

    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def populated_job(client_env):
    """Populates a job with succeeded, failed, and pending certificates and real PDFs."""
    _, TestingSession, test_storage = client_env
    db = TestingSession()

    cert_info = {
        "title": "Certificate of Mastery",
        "event_name": "Full Stack Backend Architecture",
        "issuer": "Aereo",
        "issue_date": "October 9, 2026",
    }
    job = Job(certificate_info=cert_info, status=JobStatus.PROCESSING)
    db.add(job)
    db.flush()

    # 1. Succeeded Cert 1
    pdf1 = render_certificate("Alice Johnson", cert_info, "CERT-ALICE-1")
    path1 = test_storage.save(f"{job.id}/cert1.pdf", pdf1)
    c1 = Certificate(
        job_id=job.id,
        row_index=0,
        recipient_name="Alice Johnson",
        recipient_email="alice@example.com",
        status=CertificateStatus.SUCCEEDED,
        verification_code="CERT-ALICE-1",
        file_path=path1,
        completed_at=datetime.now(timezone.utc),
    )

    # 2. Succeeded Cert 2
    pdf2 = render_certificate("आयुष आनंद", cert_info, "CERT-AYUSH-2")
    path2 = test_storage.save(f"{job.id}/cert2.pdf", pdf2)
    c2 = Certificate(
        job_id=job.id,
        row_index=1,
        recipient_name="आयुष आनंद",
        recipient_email="ayush@example.com",
        status=CertificateStatus.SUCCEEDED,
        verification_code="CERT-AYUSH-2",
        file_path=path2,
        completed_at=datetime.now(timezone.utc),
    )

    # 3. Failed Cert 3
    c3 = Certificate(
        job_id=job.id,
        row_index=2,
        recipient_name="Bad User",
        recipient_email="bad@example.com",
        status=CertificateStatus.FAILED,
        verification_code="CERT-BAD-3",
        attempts=1,
        error_code="RENDER_ERROR",
        error_message="Font rendering glitch",
    )

    # 4. Pending Cert 4
    c4 = Certificate(
        job_id=job.id,
        row_index=3,
        recipient_name="Pending User",
        recipient_email="pending@example.com",
        status=CertificateStatus.PENDING,
        verification_code="CERT-PENDING-4",
    )

    db.add_all([c1, c2, c3, c4])
    db.commit()
    job_id = job.id
    c1_id = c1.id
    c3_id = c3.id
    db.close()

    return job_id, c1_id, c3_id


def test_get_job_progress(client_env, populated_job):
    """Verify GET /v1/jobs/{id} returns accurate aggregate counts and percent complete."""
    client, _, _ = client_env
    job_id, _, _ = populated_job

    resp = client.get(f"/v1/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["job_id"] == str(job_id)
    assert data["status"] == "processing"
    prog = data["progress"]
    assert prog["total"] == 4
    assert prog["succeeded"] == 2
    assert prog["failed"] == 1
    assert prog["pending"] == 1
    assert prog["rejected"] == 0
    assert prog["percent_complete"] == 75.0  # 3 of 4 resolved
    assert data["download_url"] == f"/v1/jobs/{job_id}/download"


def test_get_job_certificates_filter(client_env, populated_job):
    """Verify GET /v1/jobs/{id}/certificates supports status filtering."""
    client, _, _ = client_env
    job_id, _, _ = populated_job

    # 1. Filter by failed
    resp_failed = client.get(f"/v1/jobs/{job_id}/certificates?status=failed")
    assert resp_failed.status_code == 200
    data_failed = resp_failed.json()
    assert data_failed["total"] == 1
    assert len(data_failed["items"]) == 1
    assert data_failed["items"][0]["recipient_name"] == "Bad User"
    assert data_failed["items"][0]["error_message"] == "Font rendering glitch"

    # 2. Filter by succeeded
    resp_succ = client.get(f"/v1/jobs/{job_id}/certificates?status=succeeded")
    assert resp_succ.status_code == 200
    data_succ = resp_succ.json()
    assert data_succ["total"] == 2
    assert len(data_succ["items"]) == 2


def test_download_single_certificate(client_env, populated_job):
    """Verify downloading a single certificate returns valid PDF binary stream."""
    client, _, _ = client_env
    _, c1_id, _ = populated_job

    resp = client.get(f"/v1/certificates/{c1_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-")


def test_download_bulk_zip(client_env, populated_job):
    """
    CRITICAL REQUIREMENT TEST:
    Verify that GET /v1/jobs/{id}/download streams a valid ZIP archive
    containing all succeeded certificates.
    """
    client, _, _ = client_env
    job_id, _, _ = populated_job

    resp = client.get(f"/v1/jobs/{job_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert f"certificates_{job_id}.zip" in resp.headers["content-disposition"]

    # Verify ZIP validity and contents
    zip_bytes = io.BytesIO(resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as z:
        file_list = z.namelist()
        assert len(file_list) == 2  # Exactly 2 succeeded certs
        # Verify uncompressed files are valid PDFs
        for name in file_list:
            pdf_data = z.read(name)
            assert pdf_data.startswith(b"%PDF-")


def test_retry_failed_certificates(client_env, populated_job):
    """Verify POST /v1/jobs/{id}/retry-failed re-queues only failed certificates."""
    client, TestingSession, _ = client_env
    job_id, _, c3_id = populated_job

    resp = client.post(f"/v1/jobs/{job_id}/retry-failed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["requeued_count"] == 1

    # Verify certificate status updated to PENDING in DB
    db = TestingSession()
    cert = db.query(Certificate).filter_by(id=c3_id).first()
    assert cert.status == CertificateStatus.PENDING
    assert cert.error_message is None
    db.close()


def test_verify_certificate_endpoint(client_env, populated_job):
    """Verify public verification route for both JSON and HTML representations."""
    client, _, _ = client_env

    # 1. Verified code (JSON)
    resp_json = client.get("/verify/CERT-ALICE-1", headers={"accept": "application/json"})
    assert resp_json.status_code == 200
    json_data = resp_json.json()
    assert json_data["valid"] is True
    assert json_data["recipient_name"] == "Alice Johnson"
    assert json_data["issuer"] == "Aereo"

    # 2. Verified code (HTML for phone camera browser)
    resp_html = client.get("/verify/CERT-ALICE-1", headers={"accept": "text/html"})
    assert resp_html.status_code == 200
    assert "text/html" in resp_html.headers["content-type"]
    assert "OFFICIAL CERTIFICATE VERIFIED" in resp_html.text
    assert "Alice Johnson" in resp_html.text

    # 3. Invalid/unknown code (404)
    resp_invalid = client.get("/verify/NON-EXISTENT-CODE", headers={"accept": "application/json"})
    assert resp_invalid.status_code == 404
    assert resp_invalid.json()["valid"] is False
