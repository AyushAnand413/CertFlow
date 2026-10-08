import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.models import Base, Job, Certificate, JobStatus, CertificateStatus


@pytest.fixture
def db_session():
    """Provides a fresh, isolated in-memory database session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


def test_settings_load_defaults():
    """Verify application configuration loads default parameters correctly."""
    settings = get_settings()
    assert settings.APP_NAME == "CertFlow"
    assert settings.WORKER_BATCH_SIZE == 50
    assert settings.WORKER_LOCK_TIMEOUT_SECONDS == 120
    assert settings.MAX_ATTEMPTS == 3
    assert settings.MAX_RECIPIENTS_PER_JOB == 10000


def test_table_metadata_and_indexes():
    """Verify both tables exist and composite indexes are defined on Certificate."""
    tables = Base.metadata.tables
    assert "jobs" in tables
    assert "certificates" in tables

    cert_table = tables["certificates"]
    index_names = {idx.name for idx in cert_table.indexes}
    assert "idx_certs_claim" in index_names
    assert "idx_certs_job_status" in index_names


def test_create_job_with_defaults(db_session):
    """Verify Job creation with automatic UUID and default status."""
    job = Job(
        certificate_info={
            "title": "Python Backend Mastery",
            "issuer": "Engineering Institute",
            "issue_date": "2026-10-09",
        },
        idempotency_key="key-test-001",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert isinstance(job.id, uuid.UUID)
    assert job.status == JobStatus.QUEUED
    assert job.certificate_info["title"] == "Python Backend Mastery"
    assert job.idempotency_key == "key-test-001"
    assert job.created_at is not None


def test_create_job_and_certificates_relationship(db_session):
    """Verify 1-to-many relationship between Job and Certificates."""
    job = Job(
        certificate_info={"title": "Bootcamp"},
    )
    cert1 = Certificate(
        job=job,
        row_index=0,
        recipient_name="Ayush Anand",
        recipient_email="ayush@example.com",
        verification_code="CERT-AAA-111",
    )
    cert2 = Certificate(
        job=job,
        row_index=1,
        recipient_name="आयुष आनंद",
        recipient_email="ayush.hi@example.com",
        verification_code="CERT-BBB-222",
    )
    db_session.add_all([job, cert1, cert2])
    db_session.commit()

    # Query back
    saved_job = db_session.query(Job).filter_by(id=job.id).first()
    assert len(saved_job.certificates) == 2
    assert saved_job.certificates[0].recipient_name == "Ayush Anand"
    assert saved_job.certificates[0].status == CertificateStatus.PENDING
    assert saved_job.certificates[0].attempts == 0
    assert saved_job.certificates[1].recipient_name == "आयुष आनंद"


def test_cascade_delete_job_removes_certificates(db_session):
    """Verify that deleting a Job cascades and automatically deletes its Certificates."""
    job = Job(certificate_info={"title": "Cascade Test"})
    cert = Certificate(
        job=job,
        row_index=0,
        recipient_name="Alice",
        recipient_email="alice@example.com",
        verification_code="CERT-CASCADE-999",
    )
    db_session.add_all([job, cert])
    db_session.commit()

    cert_id = cert.id
    # Delete parent job
    db_session.delete(job)
    db_session.commit()

    # Verify certificate was deleted by cascade
    found_cert = db_session.query(Certificate).filter_by(id=cert_id).first()
    assert found_cert is None


def test_unique_idempotency_key_constraint(db_session):
    """Verify that duplicate idempotency keys raise an IntegrityError."""
    job1 = Job(
        certificate_info={"title": "Batch 1"},
        idempotency_key="duplicate-key-123",
    )
    job2 = Job(
        certificate_info={"title": "Batch 2"},
        idempotency_key="duplicate-key-123",
    )
    db_session.add(job1)
    db_session.commit()

    db_session.add(job2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unique_verification_code_constraint(db_session):
    """Verify that duplicate verification codes raise an IntegrityError."""
    job1 = Job(certificate_info={"title": "Unique Code Test 1"})
    cert1 = Certificate(
        job=job1,
        row_index=0,
        recipient_name="User 1",
        recipient_email="user1@example.com",
        verification_code="DUPLICATE-CODE",
    )
    db_session.add_all([job1, cert1])
    db_session.commit()

    job2 = Job(certificate_info={"title": "Unique Code Test 2"})
    cert2 = Certificate(
        job=job2,
        row_index=0,
        recipient_name="User 2",
        recipient_email="user2@example.com",
        verification_code="DUPLICATE-CODE",
    )
    db_session.add_all([job2, cert2])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
