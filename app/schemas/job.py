import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.schemas.recipient import RecipientInput, RecipientSummary


class CertificateInfo(BaseModel):
    """Event & certificate layout metadata common to all recipients in the batch."""
    title: str = Field(default="Certificate of Excellence", min_length=1, max_length=128)
    event_name: str = Field(..., description="Name of the course or event", min_length=1, max_length=255)
    issuer: str = Field(default="Aereo", min_length=1, max_length=128)
    issue_date: str = Field(..., description="Date of issuance", min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)

    model_config = {
        "extra": "allow",
    }


class JobCreateRequest(BaseModel):
    """Bulk job creation request containing event info and list of recipients."""
    certificate_info: CertificateInfo
    recipients: List[RecipientInput] = Field(
        ...,
        min_length=1,
        description="List of recipients to generate certificates for (at least 1)",
    )


class JobCreateResponse(BaseModel):
    """Response returned immediately upon accepting a bulk generation job (202 Accepted)."""
    job_id: uuid.UUID
    status: str
    total: int
    accepted: int
    rejected: int
    status_url: str
    created_at: datetime
    rejected_recipients: List[RecipientSummary] = Field(default_factory=list)
