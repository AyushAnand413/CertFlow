from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.jobs import router as jobs_router
from app.api.certificates import router as certificates_router
from app.api.verify import router as verify_router
from app.config import get_settings
from app.db.models import Base
from app.db.session import engine

settings = get_settings()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    # Ensure database schema is created on application startup if DB is reachable
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        # In test environments or when database connection is deferred/mocked
        pass
    yield


app = FastAPI(
    title="CertFlow — Bulk Certificate Generator",
    description="High-throughput asynchronous backend API for generating and verifying bulk certificates.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS for frontend and API consumers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(jobs_router)
app.include_router(certificates_router)
app.include_router(verify_router)

# Mount the interactive frontend dashboard
if FRONTEND_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="dashboard")


@app.get("/", tags=["General"])
def root(request: Request):
    """Root entrypoint redirecting browsers to the SaaS Dashboard and returning JSON for API clients."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and FRONTEND_DIR.exists():
        return RedirectResponse(url="/dashboard/")
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "dashboard_url": "/dashboard",
        "docs_url": "/docs",
        "version": "0.1.0",
    }


@app.get("/health", tags=["General"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint verifying API liveness and database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "database": db_status,
        "environment": settings.ENV,
    }
