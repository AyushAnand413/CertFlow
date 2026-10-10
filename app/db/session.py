from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()

# Configure engine kwargs depending on backend (PostgreSQL vs SQLite)
engine_kwargs = {
    "echo": settings.DEBUG,
}

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite configuration for fast unit testing & local fallback with concurrency resilience
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
    if ":memory:" in settings.DATABASE_URL:
        engine_kwargs["poolclass"] = StaticPool
else:
    # Production-grade PostgreSQL connection pooling
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_pre_ping": True,  # Test connection liveness before checking out
        }
    )

from sqlalchemy import event

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

if settings.DATABASE_URL.startswith("sqlite") and ":memory:" not in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
