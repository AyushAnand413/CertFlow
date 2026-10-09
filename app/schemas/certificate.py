import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CertificateItemResponse(BaseModel):
    """Detailed response for an individual certificate."""
    id: uuid.UUID
    job_id: uuid.UUID
    row_index: int
    recipient_name: str
    recipient_email: str
    status: str
    attempts: int
    verification_code: str
    file_path: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class CertificateListResponse(BaseModel):
    """Paginated list of certificates for a job."""
    items: List[CertificateItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RetryFailedResponse(BaseModel):
    """Response returned when re-queueing failed certificates."""
    job_id: uuid.UUID
    requeued_count: int
    message: str


class VerifyCertificateResponse(BaseModel):
    """Public verification details for a certificate code."""
    valid: bool
    verification_code: str
    recipient_name: Optional[str] = None
    event_name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
