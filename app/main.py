from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
FAVICON_PATH = FRONTEND_DIR / "favicon.svg"


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
    title="CertFlow - Bulk Certificate Generator",
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


@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the CertFlow purple award SVG favicon for browser tabs."""
    return FileResponse(str(FAVICON_PATH), media_type="image/svg+xml")


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
def health_check(request: Request, format: str | None = None, db: Session = Depends(get_db)):
    """Health check endpoint returning an HTML status page for browsers and JSON for API clients."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    overall_status = "ok" if db_status == "healthy" else "degraded"
    payload = {
        "status": overall_status,
        "database": db_status,
        "environment": settings.ENV,
    }

    accept = request.headers.get("accept", "")
    if format != "json" and "text/html" in accept and "application/json" not in accept:
        is_ok = overall_status == "ok"
        badge_bg = "#ecfdf5" if is_ok else "#fef2f2"
        badge_border = "#a7f3d0" if is_ok else "#fecaca"
        badge_text = "#065f46" if is_ok else "#991b1b"
        dot_color = "#10b981" if is_ok else "#ef4444"
        headline = "All Systems Operational" if is_ok else "System Degraded"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CertFlow - System Status & API Overview</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="shortcut icon" href="/favicon.ico" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: radial-gradient(circle at top right, #f3e8ff 0%, #f8fafc 45%, #ffffff 100%);
            color: #0f172a;
            min-height: 100vh;
            padding: 32px 20px 64px;
        }}
        .container {{ max-width: 920px; margin: 0 auto; }}
        .nav {{
            display: flex; align-items: center; justify-content: space-between;
            padding-bottom: 28px; margin-bottom: 28px; border-bottom: 1px solid #e2e8f0;
            flex-wrap: wrap; gap: 12px;
        }}
        .brand {{ display: flex; align-items: center; gap: 10px; text-decoration: none; color: #0f172a; font-weight: 800; font-size: 1.35rem; letter-spacing: -0.02em; }}
        .brand-accent {{ color: #7c3aed; }}
        .brand-icon {{
            width: 38px; height: 38px; border-radius: 10px;
            background: linear-gradient(135deg, #8b5cf6, #6d28d9);
            color: #fff; display: flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 10px rgba(124, 58, 237, 0.25);
        }}
        .nav-links {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn {{
            text-decoration: none; font-size: 0.875rem; font-weight: 600;
            padding: 9px 16px; border-radius: 9px; transition: all 0.15s ease;
            border: 1px solid #e2e8f0; background: #ffffff; color: #334155;
        }}
        .btn:hover {{ border-color: #cbd5e1; background: #f8fafc; }}
        .btn-primary {{
            background: #7c3aed; color: #ffffff; border-color: #7c3aed;
        }}
        .btn-primary:hover {{ background: #6d28d9; border-color: #6d28d9; }}
        .banner {{
            background: {badge_bg}; border: 1px solid {badge_border};
            border-radius: 16px; padding: 24px 28px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 16px; margin-bottom: 24px;
        }}
        .banner-left {{ display: flex; align-items: center; gap: 14px; }}
        .pulse-dot {{
            width: 14px; height: 14px; border-radius: 50%; background: {dot_color};
            box-shadow: 0 0 0 5px rgba(16, 185, 129, 0.2);
        }}
        .banner h1 {{ font-size: 1.35rem; font-weight: 800; color: {badge_text}; }}
        .banner p {{ font-size: 0.875rem; color: #475569; margin-top: 2px; }}
        .env-pill {{
            font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.05em;
            background: #ffffff; color: #334155; padding: 6px 12px;
            border-radius: 999px; border: 1px solid #cbd5e1;
        }}
        .grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px; margin-bottom: 28px;
        }}
        .card {{
            background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
            padding: 20px; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
        }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .card-title {{ font-size: 0.9rem; font-weight: 700; color: #334155; }}
        .status-tag {{
            font-size: 0.75rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;
            background: #ecfdf5; color: #059669;
        }}
        .card-sub {{ font-size: 0.82rem; color: #64748b; line-height: 1.5; }}
        .section {{
            background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px;
            padding: 24px; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
        }}
        .section h2 {{ font-size: 1.05rem; font-weight: 800; margin-bottom: 16px; color: #0f172a; }}
        .ep-row {{
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 0; border-bottom: 1px solid #f1f5f9; gap: 12px; flex-wrap: wrap;
        }}
        .ep-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
        .ep-left {{ display: flex; align-items: center; gap: 10px; }}
        .method {{
            font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; font-weight: 700;
            padding: 4px 8px; border-radius: 6px; min-width: 52px; text-align: center;
        }}
        .m-post {{ background: #eff6ff; color: #2563eb; }}
        .m-get {{ background: #f0fdf4; color: #16a34a; }}
        .path {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 600; color: #0f172a; }}
        .desc {{ font-size: 0.85rem; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="nav">
            <a href="/dashboard/" class="brand">
                <span class="brand-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>
                </span>
                <span>Cert<span class="brand-accent">Flow</span> Status</span>
            </a>
            <div class="nav-links">
                <a href="/dashboard/" class="btn btn-primary">Open Web Dashboard</a>
                <a href="/docs" class="btn">Swagger API Docs</a>
                <a href="/redoc" class="btn">ReDoc</a>
                <a href="/health?format=json" class="btn">Raw JSON</a>
            </div>
        </nav>

        <div class="banner">
            <div class="banner-left">
                <span class="pulse-dot"></span>
                <div>
                    <h1>{headline}</h1>
                    <p>FastAPI HTTP Server, PostgreSQL Queue, and ReportLab Worker Daemon</p>
                </div>
            </div>
            <span class="env-pill">ENV: {settings.ENV}</span>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">FastAPI HTTP Engine</span>
                    <span class="status-tag">Operational</span>
                </div>
                <p class="card-sub">Async REST endpoints serving batch ingestion, progress polling, and streaming ZIP downloads.</p>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">PostgreSQL Queue</span>
                    <span class="status-tag">{db_status.upper()}</span>
                </div>
                <p class="card-sub">Connected via connection pool with row-level <code>FOR UPDATE SKIP LOCKED</code> worker coordination.</p>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">PDF & QR Worker</span>
                    <span class="status-tag">Active</span>
                </div>
                <p class="card-sub">ReportLab vector PDF engine with embedded QR verification codes and constant-memory ZIP streaming.</p>
            </div>
        </div>

        <div class="section">
            <h2>Core API Endpoints</h2>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-post">POST</span><span class="path">/v1/jobs</span></div>
                <span class="desc">Submit bulk certificate generation job (returns HTTP 202 Accepted)</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-get">GET</span><span class="path">/v1/jobs/{{job_id}}</span></div>
                <span class="desc">Poll real-time job progress, summary counts, and status</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-get">GET</span><span class="path">/v1/jobs/{{job_id}}/certificates</span></div>
                <span class="desc">List per-recipient certificate records with status filtering & pagination</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-get">GET</span><span class="path">/v1/jobs/{{job_id}}/download</span></div>
                <span class="desc">Stream all completed certificates as a ZIP archive in O(1) RAM</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-get">GET</span><span class="path">/v1/certificates/{{id}}/download</span></div>
                <span class="desc">Download an individual recipient's generated PDF certificate</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-post">POST</span><span class="path">/v1/jobs/{{job_id}}/retry-failed</span></div>
                <span class="desc">Re-queue only failed certificates in a job without regenerating succeeded ones</span>
            </div>
            <div class="ep-row">
                <div class="ep-left"><span class="method m-get">GET</span><span class="path">/verify/{{code}}</span></div>
                <span class="desc">Public QR code verification badge (HTML in browser, JSON for API clients)</span>
            </div>
        </div>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    return payload

