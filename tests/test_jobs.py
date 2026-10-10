import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.models import Base, Job, Certificate, CertificateStatus
from app.main import app


@pytest.fixture
def client_and_db():
    """Provides a TestClient with an isolated in-memory SQLite database override."""
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
    with TestClient(app) as client:
        yield client, TestingSession

    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def sample_payload():
    """Returns a valid job creation payload."""
    return {
        "certificate_info": {
            "title": "Certificate of Excellence",
            "event_name": "Distributed Backend Architecture",
            "issuer": "Aereo",
            "issue_date": "October 9, 2026",
            "description": "Demonstrated mastery of resilient queue systems.",
        },
        "recipients": [
            {"name": "Ayush Anand", "email": "ayush@example.com"},
            {"name": "आयुष आनंद", "email": "ayush.hi@example.com"},
            {"name": "Dr. Bartholomew Alexander", "email": "bart@example.com"},
        ],
    }


def test_health_check_endpoint(client_and_db):
    """Verify GET /health returns 200 OK and database health status."""
    client, _ = client_and_db
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"


def test_create_job_valid_202(client_and_db, sample_payload):
    """Verify submitting valid recipients returns 202 Accepted and creates rows."""
    client, TestingSession = client_and_db
    response = client.post("/v1/jobs", json=sample_payload)

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["total"] == 3
    assert data["accepted"] == 3
    assert data["rejected"] == 0
    assert data["status_url"] == f"/v1/jobs/{data['job_id']}"
    assert data["rejected_recipients"] == []

    # Verify rows in database
    db = TestingSession()
    job = db.query(Job).filter_by(id=uuid.UUID(data["job_id"])).first()
    assert job is not None
    assert len(job.certificates) == 3
    for cert in job.certificates:
        assert cert.status == CertificateStatus.PENDING
    db.close()


def test_partial_success_with_rejected_rows(client_and_db, sample_payload):
    """
    CRITICAL REQUIREMENT TEST:
    Verify that an invalid recipient email does not fail the batch.
    Valid recipients are queued as PENDING, and invalid ones are recorded as REJECTED with reason.
    """
    client, TestingSession = client_and_db
    payload = {
        **sample_payload,
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Invalid User", "email": "this-is-not-an-email"},
            {"name": "Another Valid", "email": "another@example.com"},
        ],
    }
    response = client.post("/v1/jobs", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["total"] == 3
    assert data["accepted"] == 2
    assert data["rejected"] == 1
    assert len(data["rejected_recipients"]) == 1

    rej = data["rejected_recipients"][0]
    assert rej["row_index"] == 1
    assert rej["name"] == "Invalid User"
    assert rej["status"] == "rejected"
    assert "Invalid email format" in rej["error_message"]

    # Verify DB statuses
    db = TestingSession()
    job = db.query(Job).filter_by(id=uuid.UUID(data["job_id"])).first()
    assert len(job.certificates) == 3
    statuses = [c.status for c in job.certificates]
    assert statuses.count(CertificateStatus.PENDING) == 2
    assert statuses.count(CertificateStatus.REJECTED) == 1
    db.close()


def test_strict_mode_rejection_422(client_and_db, sample_payload):
    """Verify that ?strict=true rejects the entire request with 422 if any recipient is invalid."""
    client, _ = client_and_db
    payload = {
        **sample_payload,
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Invalid User", "email": "bad-email"},
        ],
    }
    response = client.post("/v1/jobs?strict=true", json=payload)
    assert response.status_code == 422
    assert "Strict mode validation failed" in response.json()["detail"]


def test_idempotency_key_deduplication(client_and_db, sample_payload):
    """
    CRITICAL REQUIREMENT TEST:
    Verify that repeating the same POST request with an Idempotency-Key
    returns the existing job without creating duplicate jobs or rows.
    """
    client, TestingSession = client_and_db
    headers = {"Idempotency-Key": "unique-batch-key-999"}

    # 1. First submission
    resp1 = client.post("/v1/jobs", json=sample_payload, headers=headers)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]

    # 2. Second submission with identical key
    resp2 = client.post("/v1/jobs", json=sample_payload, headers=headers)
    assert resp2.status_code == 202
    job_id_2 = resp2.json()["job_id"]

    # Must return identical job_id
    assert job_id_1 == job_id_2

    # Verify only ONE job exists in the database
    db = TestingSession()
    jobs = db.query(Job).filter_by(idempotency_key="unique-batch-key-999").all()
    assert len(jobs) == 1
    db.close()


def test_empty_recipients_fails_422(client_and_db, sample_payload):
    """Verify submitting an empty recipient list fails with 422 Unprocessable Entity."""
    client, _ = client_and_db
    payload = {**sample_payload, "recipients": []}
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_blank_recipient_name_fails_422(client_and_db, sample_payload):
    """Verify submitting a whitespace-only recipient name fails validation with 422."""
    client, _ = client_and_db
    payload = {
        **sample_payload,
        "recipients": [{"name": "   ", "email": "user@example.com"}],
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422
