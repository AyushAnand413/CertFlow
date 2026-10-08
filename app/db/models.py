import enum
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    func,
    Enum as SAEnum,
    Uuid,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy entities."""
    pass


class JobStatus(str, enum.Enum):
    """Lifecycle statuses for a bulk generation job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class CertificateStatus(str, enum.Enum):
    """Lifecycle statuses for an individual recipient certificate."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class Job(Base):
    """Represents a bulk certificate generation job submitted by a client."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Job lifecycle status
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )

    # Common certificate metadata (title, issuer, issue_date, description, etc.)
    certificate_info: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    # Idempotency key supplied by client to prevent duplicate job creation
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # One-to-many relationship with certificates
    certificates: Mapped[List["Certificate"]] = relationship(
        "Certificate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.row_index",
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} status={self.status}>"


class Certificate(Base):
    """Represents an individual recipient certificate within a bulk job."""

    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key referencing parent job
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 0-indexed position within original user request array
    row_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Recipient details
    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Certificate lifecycle status
    status: Mapped[CertificateStatus] = mapped_column(
        SAEnum(CertificateStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=CertificateStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Retries & failure tracking
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Public verification & storage
    verification_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    # Distributed worker lease (stale-lock recovery)
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship back to parent job
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="certificates",
    )

    __table_args__ = (
        # Index for high-throughput worker queue claiming with SKIP LOCKED
        Index("idx_certs_claim", "status", "locked_until"),
        # Index for sub-millisecond job progress aggregation
        Index("idx_certs_job_status", "job_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Certificate id={self.id} job_id={self.job_id} status={self.status} recipient={self.recipient_name}>"
