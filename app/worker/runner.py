import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Certificate, CertificateStatus
from app.db.session import SessionLocal
from app.storage import get_storage
from app.storage.base import BaseStorage
from app.worker.processor import process_batch

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Worker] %(message)s",
)
logger = logging.getLogger(__name__)


def claim_next_batch(
    db: Session,
    batch_size: int = 50,
    lock_timeout_seconds: int = 120,
) -> List[uuid.UUID]:
    """
    Atomically claims a batch of pending or stale certificates using
    PostgreSQL's SELECT ... FOR UPDATE SKIP LOCKED.
    Falls back gracefully to standard locking on SQLite for local test fixtures.
    """
    # SQLite stores naive datetimes; Postgres stores aware datetimes
    if db.bind and db.bind.dialect.name == "sqlite":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        now = datetime.now(timezone.utc)

    # 1. Select candidate rows: pending OR crashed/abandoned processing rows
    stmt = (
        select(Certificate)
        .where(
            or_(
                Certificate.status == CertificateStatus.PENDING,
                and_(
                    Certificate.status == CertificateStatus.PROCESSING,
                    Certificate.locked_until.is_not(None),
                    Certificate.locked_until < now,
                ),
            )
        )
        .order_by(Certificate.created_at.asc())
        .limit(batch_size)
    )

    # Apply row-level SKIP LOCKED on PostgreSQL
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    rows = db.execute(stmt).scalars().all()
    if not rows:
        return []

    # 2. Acquire lease on claimed rows
    claimed_ids: List[uuid.UUID] = []
    lease_until = now + timedelta(seconds=lock_timeout_seconds)

    for row in rows:
        row.status = CertificateStatus.PROCESSING
        row.locked_until = lease_until
        claimed_ids.append(row.id)

    db.commit()
    logger.info(f"Claimed batch of {len(claimed_ids)} certificates (lease expires at {lease_until.isoformat()}).")
    return claimed_ids


class WorkerRunner:
    """Continuous worker daemon managing batch claiming, execution, and graceful shutdown."""

    def __init__(
        self,
        batch_size: Optional[int] = None,
        poll_interval: Optional[float] = None,
        lock_timeout_seconds: Optional[int] = None,
        storage: Optional[BaseStorage] = None,
    ):
        settings = get_settings()
        self.batch_size = batch_size or settings.WORKER_BATCH_SIZE
        self.poll_interval = poll_interval or settings.WORKER_POLL_INTERVAL_SECONDS
        self.lock_timeout_seconds = lock_timeout_seconds or settings.WORKER_LOCK_TIMEOUT_SECONDS
        self.storage = storage or get_storage()
        self.stop_requested = False

        # Register graceful shutdown signals (SIGINT, SIGTERM)
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            # Non-main thread or unsupported OS platform
            pass

    def _handle_signal(self, signum: int, frame: Any) -> None:
        signame = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info(f"Received shutdown signal ({signame}). Completing active item before stopping...")
        self.stop_requested = True

    def run(self, once: bool = False) -> int:
        """
        Runs the worker execution loop.
        If once=True, processes available queued batches and exits (ideal for deterministic tests).
        """
        logger.info("Worker runner started. Polling for generation tasks...")
        total_processed = 0

        while not self.stop_requested:
            db = SessionLocal()
            try:
                claimed_ids = claim_next_batch(
                    db=db,
                    batch_size=self.batch_size,
                    lock_timeout_seconds=self.lock_timeout_seconds,
                )

                if claimed_ids:
                    stats = process_batch(db=db, certificate_ids=claimed_ids, storage=self.storage)
                    total_processed += len(claimed_ids)
                    logger.info(f"Batch completed: {stats['succeeded']} succeeded, {stats['failed']} failed.")
                    # If work was found, immediately loop to claim next batch without sleeping
                    continue
                else:
                    if once:
                        break
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Unexpected worker loop exception: {e}", exc_info=True)
                if once:
                    break
                time.sleep(self.poll_interval)
            finally:
                db.close()

        logger.info(f"Worker runner stopped cleanly. Total processed: {total_processed}")
        return total_processed


if __name__ == "__main__":
    runner = WorkerRunner()
    runner.run()
