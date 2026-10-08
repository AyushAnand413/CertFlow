import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Certificate, Job, CertificateStatus, JobStatus
from app.rendering.template import render_certificate
from app.storage import get_storage
from app.storage.base import BaseStorage

logger = logging.getLogger(__name__)


def process_certificate(
    db: Session,
    certificate_id: uuid.UUID,
    storage: Optional[BaseStorage] = None,
) -> bool:
    """
    Renders and stores a single certificate with strict row-level failure isolation.
    Returns True if successfully generated, False if failed.
    """
    if storage is None:
        storage = get_storage()

    settings = get_settings()

    # 1. Fetch certificate row
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        logger.warning(f"Certificate {certificate_id} not found.")
        return False

    # Fetch parent job
    job = db.query(Job).filter(Job.id == cert.job_id).first()
    if not job:
        logger.error(f"Parent job {cert.job_id} not found for certificate {certificate_id}.")
        return False

    # Set job started_at timestamp if first certificate in job
    now = datetime.now(timezone.utc)
    if job.started_at is None:
        job.started_at = now
        job.status = JobStatus.PROCESSING
        db.commit()

    # 2. Isolated processing per certificate
    try:
        # Render vector PDF
        pdf_bytes = render_certificate(
            recipient_name=cert.recipient_name,
            certificate_info=job.certificate_info,
            verification_code=cert.verification_code,
            verification_base_url=settings.VERIFICATION_BASE_URL,
        )

        # Store PDF via abstract storage layer
        relative_path = f"{cert.job_id}/{cert.id}.pdf"
        saved_path = storage.save(relative_path, pdf_bytes)

        # Mark certificate succeeded
        cert.status = CertificateStatus.SUCCEEDED
        cert.file_path = saved_path
        cert.error_code = None
        cert.error_message = None
        cert.locked_until = None
        cert.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Certificate {cert.id} for '{cert.recipient_name}' generated successfully.")
        result = True

    except Exception as exc:
        # Failure isolation: Catch error strictly for this row so others continue
        logger.error(f"Failed to render certificate {cert.id} ({cert.recipient_name}): {exc}", exc_info=True)
        try:
            db.rollback()
            # Re-fetch row in fresh transaction to record failure
            failed_cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
            if failed_cert:
                failed_cert.status = CertificateStatus.FAILED
                failed_cert.attempts += 1
                failed_cert.error_code = "RENDER_ERROR"
                failed_cert.error_message = str(exc)
                failed_cert.locked_until = None
                failed_cert.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as db_exc:
            logger.error(f"Failed to record failure state for certificate {certificate_id}: {db_exc}")
            db.rollback()
        result = False

    # 3. Check if all certificates for the parent job are completed
    _check_and_update_job_completion(db, cert.job_id)

    return result


def _check_and_update_job_completion(db: Session, job_id: uuid.UUID) -> None:
    """Updates parent job finished_at and status if all certificate rows are resolved."""
    try:
        # Count remaining unfinalized certificates
        unfinalized_count = (
            db.query(func.count(Certificate.id))
            .filter(
                Certificate.job_id == job_id,
                Certificate.status.in_([CertificateStatus.PENDING, CertificateStatus.PROCESSING]),
            )
            .scalar()
        )

        if unfinalized_count == 0:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and job.finished_at is None:
                job.finished_at = datetime.now(timezone.utc)

                # Determine final aggregate status
                failed_count = (
                    db.query(func.count(Certificate.id))
                    .filter(
                        Certificate.job_id == job_id,
                        Certificate.status.in_([CertificateStatus.FAILED, CertificateStatus.REJECTED]),
                    )
                    .scalar()
                )
                succeeded_count = (
                    db.query(func.count(Certificate.id))
                    .filter(
                        Certificate.job_id == job_id,
                        Certificate.status == CertificateStatus.SUCCEEDED,
                    )
                    .scalar()
                )

                if succeeded_count > 0 and failed_count > 0:
                    job.status = JobStatus.COMPLETED_WITH_ERRORS
                elif succeeded_count > 0 and failed_count == 0:
                    job.status = JobStatus.COMPLETED
                else:
                    job.status = JobStatus.FAILED

                db.commit()
    except Exception as e:
        logger.error(f"Error checking job completion for {job_id}: {e}")
        db.rollback()


def process_batch(
    db: Session,
    certificate_ids: List[uuid.UUID],
    storage: Optional[BaseStorage] = None,
) -> Dict[str, int]:
    """Processes a list of claimed certificate IDs and returns counts."""
    stats = {"succeeded": 0, "failed": 0}
    for cert_id in certificate_ids:
        if process_certificate(db, cert_id, storage=storage):
            stats["succeeded"] += 1
        else:
            stats["failed"] += 1
    return stats
