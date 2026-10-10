import re
import uuid
from typing import Generator
import zipstream
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, Job
from app.storage import get_storage
from app.storage.base import BaseStorage


def sanitize_filename(name: str) -> str:
    """Sanitizes recipient name for inclusion in archive filenames."""
    # Replace non-alphanumeric (except underscores and hyphens) with underscores
    clean = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    return clean[:50] or "certificate"


def stream_job_zip(db: Session, job_id: uuid.UUID, storage: BaseStorage = None) -> Generator[bytes, None, None]:
    """
    Streams a ZIP archive containing all succeeded certificates for a job.
    Uses zipstream to consume constant O(1) RAM regardless of batch size.
    """
    if storage is None:
        storage = get_storage()

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    succeeded_certs = (
        db.query(Certificate)
        .filter(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.SUCCEEDED,
            Certificate.file_path.is_not(None),
        )
        .order_by(Certificate.row_index.asc())
        .all()
    )

    if not succeeded_certs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No succeeded certificates are available to download for job '{job_id}'.",
        )

    # Initialize streaming ZIP generator
    zs = zipstream.ZipStream()

    for cert in succeeded_certs:
        if storage.exists(cert.file_path):
            file_stream = storage.open(cert.file_path)
            clean_name = sanitize_filename(cert.recipient_name)
            arcname = f"{cert.row_index + 1:04d}_{clean_name}_{cert.verification_code}.pdf"
            zs.add(file_stream, arcname=arcname)

    for chunk in zs:
        yield chunk
