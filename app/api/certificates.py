import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Certificate, CertificateStatus
from app.services.zip_stream import stream_job_zip, sanitize_filename
from app.storage import get_storage
from app.storage.base import BaseStorage

router = APIRouter(tags=["Certificates & Downloads"])


@router.get(
    "/v1/certificates/{certificate_id}/download",
    summary="Download single certificate PDF",
    description="Downloads the generated PDF file for a specific succeeded certificate.",
)
def download_single_certificate(
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with ID '{certificate_id}' not found.",
        )

    if cert.status != CertificateStatus.SUCCEEDED or not cert.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate '{certificate_id}' is not ready for download (current status: '{cert.status.value}').",
        )

    if not storage.exists(cert.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage.",
        )

    clean_name = sanitize_filename(cert.recipient_name)
    filename = f"Certificate_{clean_name}_{cert.verification_code}.pdf"
    stream = storage.open(cert.file_path)

    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/v1/jobs/{job_id}/download",
    summary="Download bulk certificates as ZIP",
    description="Streams a ZIP archive containing all successfully generated certificates in constant memory.",
)
def download_job_certificates_zip(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    generator = stream_job_zip(db=db, job_id=job_id, storage=storage)
    zip_filename = f"certificates_{job_id}.zip"

    return StreamingResponse(
        generator,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )
