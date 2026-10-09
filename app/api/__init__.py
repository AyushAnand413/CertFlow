"""API routes package."""

from app.api.jobs import router as jobs_router
from app.api.certificates import router as certificates_router
from app.api.verify import router as verify_router

__all__ = ["jobs_router", "certificates_router", "verify_router"]
