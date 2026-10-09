import uuid
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Job, Certificate, JobStatus, CertificateStatus
from app.schemas.job import JobCreateRequest, JobCreateResponse
from app.schemas.recipient import RecipientSummary


def generate_verification_code() -> str:
    """Generate a clean, high-entropy unique certificate verification code."""
    return f"CERT-{uuid.uuid4().hex[:8].upper()}"


def create_job_service(
    db: Session,
    request: JobCreateRequest,
    idempotency_key: Optional[str] = None,
    strict: bool = False,
) -> JobCreateResponse:
    """
    Validates and ingests a bulk certificate generation job.
    Supports:
    - Idempotency key deduplication
    - Partial success ingestion (valid -> pending, invalid -> rejected)
    - Strict mode (reject entire request if any recipient is invalid)
    """
    settings = get_settings()

    # 1. Enforce maximum batch size
    if len(request.recipients) > settings.MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size {len(request.recipients)} exceeds maximum allowed limit of {settings.MAX_RECIPIENTS_PER_JOB}.",
        )

    # 2. Idempotency Check: Return existing job if same key was already processed
    if idempotency_key:
        clean_key = idempotency_key.strip()
        existing_job = db.query(Job).filter(Job.idempotency_key == clean_key).first()
        if existing_job:
            total = len(existing_job.certificates)
            rejected_certs = [
                RecipientSummary(
                    row_index=c.row_index,
                    name=c.recipient_name,
                    email=c.recipient_email,
                    status=c.status.value,
                    error_code=c.error_code,
                    error_message=c.error_message,
                )
                for c in existing_job.certificates
                if c.status == CertificateStatus.REJECTED
            ]
            accepted = total - len(rejected_certs)

            return JobCreateResponse(
                job_id=existing_job.id,
                status=existing_job.status.value,
                total=total,
                accepted=accepted,
                rejected=len(rejected_certs),
                status_url=f"/v1/jobs/{existing_job.id}",
                created_at=existing_job.created_at,
                rejected_recipients=rejected_certs,
            )

    # 3. If strict mode is enabled, pre-validate all recipients
    if strict:
        invalid_rows = [
            f"Row {idx}: Invalid email '{rec.email}'"
            for idx, rec in enumerate(request.recipients)
            if not rec.is_valid_email()
        ]
        if invalid_rows:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Strict mode validation failed: {'; '.join(invalid_rows)}",
            )

    # 4. Create Job entity
    job = Job(
        certificate_info=request.certificate_info.model_dump(),
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.flush()  # Populates job.id before creating child certificates

    # 5. Process recipients with Partial Success logic
    cert_rows: List[Certificate] = []
    rejected_summaries: List[RecipientSummary] = []
    accepted_count = 0

    for idx, rec in enumerate(request.recipients):
        code = generate_verification_code()

        if rec.is_valid_email():
            # Valid recipient -> queued for worker generation
            cert = Certificate(
                job_id=job.id,
                row_index=idx,
                recipient_name=rec.name,
                recipient_email=rec.email,
                status=CertificateStatus.PENDING,
                verification_code=code,
            )
            accepted_count += 1
        else:
            # Invalid recipient -> marked rejected upfront with failure reason
            error_msg = f"Invalid email format: '{rec.email}'"
            cert = Certificate(
                job_id=job.id,
                row_index=idx,
                recipient_name=rec.name,
                recipient_email=rec.email,
                status=CertificateStatus.REJECTED,
                error_code="VALIDATION_ERROR",
                error_message=error_msg,
                verification_code=code,
            )
            rejected_summaries.append(
                RecipientSummary(
                    row_index=idx,
                    name=rec.name,
                    email=rec.email,
                    status=CertificateStatus.REJECTED.value,
                    error_code="VALIDATION_ERROR",
                    error_message=error_msg,
                )
            )

        cert_rows.append(cert)

    # If all recipients were rejected, update initial job status
    if accepted_count == 0 and len(rejected_summaries) > 0:
        job.status = JobStatus.FAILED

    db.add_all(cert_rows)
    db.commit()
    db.refresh(job)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status.value,
        total=len(request.recipients),
        accepted=accepted_count,
        rejected=len(rejected_summaries),
        status_url=f"/v1/jobs/{job.id}",
        created_at=job.created_at,
        rejected_recipients=rejected_summaries,
    )
