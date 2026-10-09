import math
import uuid
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Job, Certificate, JobStatus, CertificateStatus
from app.schemas.job import JobDetailResponse, JobProgress
from app.schemas.certificate import (
    CertificateItemResponse,
    CertificateListResponse,
    RetryFailedResponse,
    VerifyCertificateResponse,
)


def get_job_progress_service(db: Session, job_id: uuid.UUID) -> JobDetailResponse:
    """Calculates granular real-time progress statistics for a bulk job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    # Sub-millisecond indexed SQL aggregation by status
    status_counts = dict(
        db.query(Certificate.status, func.count(Certificate.id))
        .filter(Certificate.job_id == job_id)
        .group_by(Certificate.status)
        .all()
    )

    total = sum(status_counts.values())
    succeeded = status_counts.get(CertificateStatus.SUCCEEDED, 0)
    failed = status_counts.get(CertificateStatus.FAILED, 0)
    rejected = status_counts.get(CertificateStatus.REJECTED, 0)
    pending = status_counts.get(CertificateStatus.PENDING, 0)
    processing = status_counts.get(CertificateStatus.PROCESSING, 0)

    finished = succeeded + failed + rejected
    percent = round((finished / total) * 100, 1) if total > 0 else 0.0

    # Derive accurate aggregate job status
    if total == 0:
        current_status = JobStatus.QUEUED.value
    elif pending == total:
        current_status = JobStatus.QUEUED.value
    elif pending > 0 or processing > 0:
        current_status = JobStatus.PROCESSING.value
    else:
        # All items resolved
        if failed == 0 and rejected == 0:
            current_status = JobStatus.COMPLETED.value
        elif succeeded > 0:
            current_status = JobStatus.COMPLETED_WITH_ERRORS.value
        else:
            current_status = JobStatus.FAILED.value

    download_url = f"/v1/jobs/{job_id}/download" if succeeded > 0 else None

    progress = JobProgress(
        total=total,
        pending=pending,
        processing=processing,
        succeeded=succeeded,
        failed=failed,
        rejected=rejected,
        percent_complete=percent,
    )

    return JobDetailResponse(
        job_id=job.id,
        status=current_status,
        certificate_info=job.certificate_info,
        progress=progress,
        download_url=download_url,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def get_job_certificates_service(
    db: Session,
    job_id: uuid.UUID,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> CertificateListResponse:
    """Returns paginated recipient certificate rows for a job, with optional status filtering."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    query = db.query(Certificate).filter(Certificate.job_id == job_id)

    if status_filter:
        clean_status = status_filter.strip().lower()
        query = query.filter(Certificate.status == clean_status)

    total = query.count()
    items = (
        query.order_by(Certificate.row_index.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    item_responses = [
        CertificateItemResponse(
            id=c.id,
            job_id=c.job_id,
            row_index=c.row_index,
            recipient_name=c.recipient_name,
            recipient_email=c.recipient_email,
            status=c.status.value,
            attempts=c.attempts,
            verification_code=c.verification_code,
            file_path=c.file_path,
            error_code=c.error_code,
            error_message=c.error_message,
            download_url=f"/v1/certificates/{c.id}/download" if c.status == CertificateStatus.SUCCEEDED else None,
            created_at=c.created_at,
            completed_at=c.completed_at,
        )
        for c in items
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return CertificateListResponse(
        items=item_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def retry_failed_certificates_service(
    db: Session,
    job_id: uuid.UUID,
) -> RetryFailedResponse:
    """Re-queues only failed certificates for a job without re-rendering succeeded ones."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    failed_certs = (
        db.query(Certificate)
        .filter(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.FAILED,
            Certificate.attempts < 3,
        )
        .all()
    )

    count = len(failed_certs)
    if count > 0:
        for c in failed_certs:
            c.status = CertificateStatus.PENDING
            c.locked_until = None
            c.error_code = None
            c.error_message = None

        job.status = JobStatus.PROCESSING
        job.finished_at = None
        db.commit()

    return RetryFailedResponse(
        job_id=job.id,
        requeued_count=count,
        message=f"Re-queued {count} failed certificates for generation." if count > 0 else "No eligible failed certificates to retry.",
    )


def verify_certificate_service(
    db: Session,
    code: str,
) -> VerifyCertificateResponse:
    """Queries verification details for a certificate code."""
    clean_code = code.strip()
    cert = db.query(Certificate).filter(Certificate.verification_code == clean_code).first()

    if not cert or cert.status != CertificateStatus.SUCCEEDED:
        return VerifyCertificateResponse(
            valid=False,
            verification_code=clean_code,
            status="INVALID",
        )

    job = db.query(Job).filter(Job.id == cert.job_id).first()
    cert_info = job.certificate_info if job else {}

    return VerifyCertificateResponse(
        valid=True,
        verification_code=clean_code,
        recipient_name=cert.recipient_name,
        event_name=cert_info.get("event_name"),
        issuer=cert_info.get("issuer"),
        issue_date=cert_info.get("issue_date"),
        status="VERIFIED",
        completed_at=cert.completed_at,
    )
