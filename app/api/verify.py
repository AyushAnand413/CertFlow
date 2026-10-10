from html import escape as html_escape
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.certificate import VerifyCertificateResponse
from app.services.progress import verify_certificate_service

router = APIRouter(tags=["Public Verification"])


@router.get(
    "/verify/{code}",
    summary="Public certificate verification",
    description="Target of certificate QR codes. Returns HTML badge for web browsers or JSON for API clients.",
)
def verify_certificate(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    result = verify_certificate_service(db=db, code=code)

    # Check if the client is a browser expecting HTML
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header:
        if result.valid:
            safe_name = html_escape(result.recipient_name or "")
            safe_event = html_escape(result.event_name or "")
            safe_issuer = html_escape(result.issuer or "")
            safe_date = html_escape(result.issue_date or "")
            safe_code = html_escape(result.verification_code or "")

            html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verified Certificate - {safe_name} | CertFlow</title>
                <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
                <link rel="shortcut icon" href="/favicon.ico" />
                <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
                <style>
                    * {{ box-sizing: border-box; }}
                    body {{ font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif; background: linear-gradient(180deg, #F3EFFE 0%, #F9F6FF 45%, #FFFFFF 100%); color: #111827; min-height: 100vh; margin: 0; display: flex; flex-direction: column; }}
                    .navbar {{ height: 76px; background: rgba(255,255,255,0.92); border-bottom: 1px solid #E5E7EB; display: flex; align-items: center; justify-content: space-between; padding: 0 32px; }}
                    .brand {{ display: flex; align-items: center; gap: 10px; text-decoration: none; color: #111827; font-weight: 800; font-size: 22px; letter-spacing: -0.02em; }}
                    .brand-icon {{ width: 38px; height: 38px; border-radius: 10px; background: #7C3AED; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-size: 18px; }}
                    .brand span {{ color: #7C3AED; }}
                    .nav-btn {{ padding: 10px 18px; border-radius: 10px; background: #FFFFFF; border: 2px solid #111827; color: #111827; font-weight: 700; font-size: 13px; text-decoration: none; transition: all 0.15s ease; }}
                    .nav-btn:hover {{ background: #F3F4F6; }}
                    .main {{ flex: 1; display: flex; justify-content: center; align-items: center; padding: 32px 16px; }}
                    .card {{ background: #FFFFFF; border: 2px solid #111827; border-radius: 24px; padding: 40px 36px; max-width: 520px; width: 100%; box-shadow: 0 8px 0 #111827, 0 20px 40px rgba(17,24,39,0.08); text-align: center; }}
                    .badge {{ background: #D1FAE5; color: #065F46; border: 1.5px solid #34D399; font-weight: 800; font-size: 12px; letter-spacing: 0.06em; padding: 7px 16px; border-radius: 9999px; display: inline-flex; align-items: center; gap: 6px; margin-bottom: 20px; }}
                    h1 {{ font-family: 'Playfair Display', Georgia, serif; font-size: 32px; margin: 0 0 8px; color: #111827; }}
                    .event {{ color: #4B5563; font-size: 15px; font-weight: 500; margin-bottom: 28px; }}
                    .detail-box {{ background: #F9F6FF; border: 1.5px solid #E9D5FF; border-radius: 16px; padding: 20px; text-align: left; margin-bottom: 24px; }}
                    .detail-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(216,180,254,0.4); font-size: 13.5px; }}
                    .detail-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
                    .detail-row:first-child {{ padding-top: 0; }}
                    .label {{ color: #6B7280; font-weight: 600; }}
                    .value {{ color: #111827; font-weight: 700; }}
                    .cta-btn {{ display: inline-block; width: 100%; padding: 14px 20px; border-radius: 12px; background: #5CE1A6; color: #091E15; font-weight: 800; font-size: 14px; text-decoration: none; border: 2px solid #111827; box-shadow: 0 4px 0 #111827; transition: all 0.15s ease; }}
                    .cta-btn:hover {{ background: #48D195; transform: translateY(-1px); }}
                    .footer {{ color: #6B7280; font-size: 12px; font-weight: 500; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <header class="navbar">
                    <a href="/dashboard/" class="brand">
                        <div class="brand-icon"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg></div>
                        <div>Cert<span>Flow</span></div>
                    </a>
                    <a href="/dashboard/" class="nav-btn">&larr; Back to Certificate Maker</a>
                </header>
                <main class="main">
                    <div class="card">
                        <div class="badge">&#10003; OFFICIAL CERTIFICATE VERIFIED</div>
                        <h1>{safe_name}</h1>
                        <div class="event">{safe_event}</div>
                        <div class="detail-box">
                            <div class="detail-row"><span class="label">Issuing Authority</span><span class="value">{safe_issuer}</span></div>
                            <div class="detail-row"><span class="label">Date of Issue</span><span class="value">{safe_date}</span></div>
                            <div class="detail-row"><span class="label">Certificate ID</span><span class="value" style="font-family:monospace;">{safe_code}</span></div>
                            <div class="detail-row"><span class="label">Status</span><span class="value" style="color:#059669;">AUTHENTIC</span></div>
                        </div>
                        <a href="/dashboard/" class="cta-btn">Create or Verify Another Certificate</a>
                        <div class="footer">Issued and cryptographically verified by Aereo CertFlow</div>
                    </div>
                </main>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=200)
        else:
            safe_invalid_code = html_escape(code)
            invalid_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Invalid Certificate | CertFlow</title>
                <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
                <link rel="shortcut icon" href="/favicon.ico" />
                <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
                <style>
                    * {{ box-sizing: border-box; }}
                    body {{ font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif; background: linear-gradient(180deg, #FEF2F2 0%, #FFFFFF 100%); color: #111827; min-height: 100vh; margin: 0; display: flex; flex-direction: column; }}
                    .navbar {{ height: 76px; background: rgba(255,255,255,0.92); border-bottom: 1px solid #E5E7EB; display: flex; align-items: center; justify-content: space-between; padding: 0 32px; }}
                    .brand {{ display: flex; align-items: center; gap: 10px; text-decoration: none; color: #111827; font-weight: 800; font-size: 22px; }}
                    .brand-icon {{ width: 38px; height: 38px; border-radius: 10px; background: #7C3AED; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-size: 18px; }}
                    .brand span {{ color: #7C3AED; }}
                    .nav-btn {{ padding: 10px 18px; border-radius: 10px; background: #FFFFFF; border: 2px solid #111827; color: #111827; font-weight: 700; font-size: 13px; text-decoration: none; }}
                    .main {{ flex: 1; display: flex; justify-content: center; align-items: center; padding: 32px 16px; }}
                    .card {{ background: #FFFFFF; border: 2px solid #111827; border-radius: 24px; padding: 40px 36px; max-width: 480px; width: 100%; box-shadow: 0 8px 0 #111827; text-align: center; }}
                    .badge {{ background: #FEE2E2; color: #991B1B; border: 1.5px solid #F87171; font-weight: 800; font-size: 12px; padding: 7px 16px; border-radius: 9999px; display: inline-flex; margin-bottom: 20px; }}
                    h1 {{ font-size: 26px; font-weight: 800; color: #111827; margin: 0 0 10px; }}
                    p {{ color: #4B5563; font-size: 14px; line-height: 1.5; margin-bottom: 20px; }}
                    .code {{ font-family: monospace; font-weight: 700; background: #FEF2F2; border: 1.5px solid #FECACA; padding: 12px; border-radius: 12px; color: #991B1B; margin-bottom: 24px; }}
                    .cta-btn {{ display: inline-block; width: 100%; padding: 14px 20px; border-radius: 12px; background: #7C3AED; color: #FFFFFF; font-weight: 700; font-size: 14px; text-decoration: none; }}
                </style>
            </head>
            <body>
                <header class="navbar">
                    <a href="/dashboard/" class="brand">
                        <div class="brand-icon"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg></div>
                        <div>Cert<span>Flow</span></div>
                    </a>
                    <a href="/dashboard/" class="nav-btn">&larr; Back to Certificate Maker</a>
                </header>
                <main class="main">
                    <div class="card">
                        <div class="badge">&#10007; VERIFICATION FAILED</div>
                        <h1>Certificate Not Found</h1>
                        <p>The code below does not correspond to an authentic issued certificate.</p>
                        <div class="code">{safe_invalid_code}</div>
                        <a href="/dashboard/#verify-section" class="cta-btn">Try Another Certificate ID</a>
                    </div>
                </main>
            </body>
            </html>
            """
            return HTMLResponse(content=invalid_html, status_code=404)

    # API / JSON response
    status_code = 200 if result.valid else 404
    return JSONResponse(content=result.model_dump(mode="json"), status_code=status_code)
