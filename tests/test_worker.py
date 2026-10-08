import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Job, Certificate, CertificateStatus, JobStatus
from app.storage.local import LocalStorage
from app.worker.processor import process_certificate, process_batch
from app.worker.runner import claim_next_batch, WorkerRunner


@pytest.fixture
def session_factory():
    """Provides an isolated test engine and session factory for tests."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    yield TestingSession
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def db_session(session_factory):
    """Provides a managed database session for a single test."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_storage(tmp_path):
    """Provides an isolated temporary storage instance."""
    return LocalStorage(str(tmp_path))


@pytest.fixture
def sample_job(db_session):
    """Creates a sample job in the database."""
    job = Job(
        certificate_info={
            "title": "Certificate of Excellence",
            "event_name": "Distributed Backend Architecture",
            "issuer": "Aereo",
            "issue_date": "October 9, 2026",
        }
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_claim_next_batch(db_session, sample_job):
    """Verify worker claims pending rows and assigns lease expiration."""
    certs = [
        Certificate(
            job=sample_job,
            row_index=i,
            recipient_name=f"User {i}",
            recipient_email=f"user{i}@example.com",
            verification_code=f"CODE-{i}",
        )
        for i in range(5)
    ]
    db_session.add_all(certs)
    db_session.commit()

    # Claim batch of size 3
    claimed_ids = claim_next_batch(db_session, batch_size=3, lock_timeout_seconds=60)
    assert len(claimed_ids) == 3

    now_cmp = datetime.now(timezone.utc).replace(tzinfo=None)

    # Verify claimed rows are PROCESSING and locked
    for cert_id in claimed_ids:
        cert = db_session.query(Certificate).filter_by(id=cert_id).first()
        assert cert.status == CertificateStatus.PROCESSING
        assert cert.locked_until is not None
        locked = cert.locked_until.replace(tzinfo=None) if cert.locked_until.tzinfo else cert.locked_until
        assert locked > now_cmp

    # Claim next batch -> should get remaining 2
    claimed_next = claim_next_batch(db_session, batch_size=3)
    assert len(claimed_next) == 2


def test_process_certificate_success(db_session, temp_storage, sample_job):
    """Verify single certificate is rendered, stored, and marked SUCCEEDED."""
    cert = Certificate(
        job=sample_job,
        row_index=0,
        recipient_name="Ayush Anand",
        recipient_email="ayush@example.com",
        verification_code="CERT-SUCCESS-001",
    )
    db_session.add(cert)
    db_session.commit()

    success = process_certificate(db_session, cert.id, storage=temp_storage)
    assert success is True

    # Verify certificate status and file
    db_session.refresh(cert)
    assert cert.status == CertificateStatus.SUCCEEDED
    assert cert.file_path is not None
    assert temp_storage.exists(cert.file_path) is True
    assert cert.completed_at is not None
    assert cert.locked_until is None

    # Verify parent job completion
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.COMPLETED
    assert sample_job.started_at is not None
    assert sample_job.finished_at is not None


def test_failure_isolation(db_session, temp_storage, sample_job):
    """
    CRITICAL REQUIREMENT TEST:
    Verify that an individual certificate failure does NOT prevent other valid certificates
    in the same batch from being generated successfully.
    """
    cert1 = Certificate(
        job=sample_job,
        row_index=0,
        recipient_name="Valid User 1",
        recipient_email="user1@example.com",
        verification_code="CERT-ISO-1",
    )
    cert2 = Certificate(
        job=sample_job,
        row_index=1,
        recipient_name="Failing User 2",
        recipient_email="user2@example.com",
        verification_code="CERT-ISO-2",
    )
    cert3 = Certificate(
        job=sample_job,
        row_index=2,
        recipient_name="Valid User 3",
        recipient_email="user3@example.com",
        verification_code="CERT-ISO-3",
    )
    db_session.add_all([cert1, cert2, cert3])
    db_session.commit()

    # Simulate render crash strictly for cert2
    original_render = __import__("app.worker.processor", fromlist=["render_certificate"]).render_certificate

    def mock_render(*args, **kwargs):
        if kwargs.get("recipient_name") == "Failing User 2":
            raise RuntimeError("Simulated render engine glitch")
        return original_render(*args, **kwargs)

    with patch("app.worker.processor.render_certificate", side_effect=mock_render):
        stats = process_batch(
            db_session,
            [cert1.id, cert2.id, cert3.id],
            storage=temp_storage,
        )

    # 2 succeeded, 1 failed
    assert stats["succeeded"] == 2
    assert stats["failed"] == 1

    db_session.refresh(cert1)
    db_session.refresh(cert2)
    db_session.refresh(cert3)
    db_session.refresh(sample_job)

    # Cert 1 succeeded
    assert cert1.status == CertificateStatus.SUCCEEDED
    assert temp_storage.exists(cert1.file_path) is True

    # Cert 2 failed gracefully with error recorded
    assert cert2.status == CertificateStatus.FAILED
    assert "Simulated render engine glitch" in cert2.error_message
    assert cert2.attempts == 1
    assert cert2.file_path is None

    # Cert 3 succeeded despite Cert 2 failing
    assert cert3.status == CertificateStatus.SUCCEEDED
    assert temp_storage.exists(cert3.file_path) is True

    # Parent job finished with errors
    assert sample_job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert sample_job.finished_at is not None


def test_crash_recovery_stale_lock(db_session, temp_storage, sample_job):
    """
    CRITICAL REQUIREMENT TEST:
    Verify that an abandoned/crashed task (locked_until expired in the past)
    is automatically reclaimed and processed to completion.
    """
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    stale_cert = Certificate(
        job=sample_job,
        row_index=0,
        recipient_name="Recovered User",
        recipient_email="recovered@example.com",
        verification_code="CERT-RECOVER-999",
        status=CertificateStatus.PROCESSING,
        locked_until=past_time,  # Expired lease
    )
    db_session.add(stale_cert)
    db_session.commit()

    # Worker polls for batch
    claimed_ids = claim_next_batch(db_session, batch_size=10)
    assert stale_cert.id in claimed_ids

    # Process reclaimed row
    success = process_certificate(db_session, stale_cert.id, storage=temp_storage)
    assert success is True

    db_session.refresh(stale_cert)
    assert stale_cert.status == CertificateStatus.SUCCEEDED
    assert stale_cert.locked_until is None


def test_worker_runner_run_once(session_factory, temp_storage):
    """Verify WorkerRunner processes queued items in 'run once' mode."""
    db = session_factory()
    job = Job(certificate_info={"title": "Runner Test", "issuer": "Aereo"})
    cert = Certificate(
        job=job,
        row_index=0,
        recipient_name="Runner User",
        recipient_email="runner@example.com",
        verification_code="CERT-RUNNER-1",
    )
    db.add_all([job, cert])
    db.commit()
    cert_id = cert.id
    db.close()

    with patch("app.worker.runner.SessionLocal", side_effect=session_factory):
        runner = WorkerRunner(storage=temp_storage, poll_interval=0.01)
        total = runner.run(once=True)

    assert total >= 1

    verify_db = session_factory()
    saved_cert = verify_db.query(Certificate).filter_by(id=cert_id).first()
    assert saved_cert.status == CertificateStatus.SUCCEEDED
    verify_db.close()
