import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobDetailResponse
from app.schemas.certificate import CertificateListResponse, RetryFailedResponse
from app.services.job_service import create_job_service
from app.services.progress import (
    get_job_progress_service,
    get_job_certificates_service,
    retry_failed_certificates_service,
)

router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit bulk certificate generation job",
    description="Accepts certificate metadata and a list of recipients. Validates entries and queues valid recipients for background generation.",
)
def create_job(
    request: JobCreateRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    strict: bool = Query(False, description="If True, reject entire request with 422 if any recipient is invalid."),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    return create_job_service(
        db=db,
        request=request,
        idempotency_key=idempotency_key,
        strict=strict,
    )


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Get job progress and status",
    description="Returns aggregate progress statistics, completion percentage, and download URL.",
)
def get_job_progress(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JobDetailResponse:
    return get_job_progress_service(db=db, job_id=job_id)


@router.get(
    "/{job_id}/certificates",
    response_model=CertificateListResponse,
    summary="List certificates for a job",
    description="Returns paginated certificates with optional filtering by status (e.g. ?status=failed).",
)
def get_job_certificates(
    job_id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter certificates by status (pending, processing, succeeded, failed, rejected)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_db),
) -> CertificateListResponse:
    return get_job_certificates_service(
        db=db,
        job_id=job_id,
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{job_id}/retry-failed",
    response_model=RetryFailedResponse,
    summary="Retry failed certificates",
    description="Re-queues only failed certificates for a job without re-rendering succeeded ones.",
)
def retry_failed_certificates(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RetryFailedResponse:
    return retry_failed_certificates_service(db=db, job_id=job_id)
