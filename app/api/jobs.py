from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.job import JobCreateRequest, JobCreateResponse
from app.services.job_service import create_job_service

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
