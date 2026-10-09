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
                <title>Verified Certificate — {safe_name}</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0F172A; color: #F8FAFC; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 16px; box-sizing: border-box; }}
                    .card {{ background: #1E293B; border: 1px solid #334155; border-radius: 16px; padding: 32px; max-width: 480px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; }}
                    .badge {{ background: #065F46; color: #34D399; font-weight: 700; font-size: 13px; letter-spacing: 0.05em; padding: 6px 16px; border-radius: 9999px; display: inline-flex; align-items: center; margin-bottom: 24px; }}
                    h1 {{ font-size: 24px; margin: 0 0 8px; color: #FFFFFF; }}
                    .event {{ color: #94A3B8; font-size: 15px; margin-bottom: 24px; }}
                    .detail-box {{ background: #0F172A; border-radius: 8px; padding: 16px; text-align: left; margin-bottom: 20px; }}
                    .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }}
                    .detail-row:last-child {{ margin-bottom: 0; }}
                    .label {{ color: #64748B; }}
                    .value {{ color: #E2E8F0; font-weight: 600; }}
                    .footer {{ color: #475569; font-size: 12px; margin-top: 16px; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="badge">&#10003; OFFICIAL CERTIFICATE VERIFIED</div>
                    <h1>{safe_name}</h1>
                    <div class="event">{safe_event}</div>
                    <div class="detail-box">
                        <div class="detail-row"><span class="label">Issuing Authority:</span><span class="value">{safe_issuer}</span></div>
                        <div class="detail-row"><span class="label">Date of Issue:</span><span class="value">{safe_date}</span></div>
                        <div class="detail-row"><span class="label">Certificate ID:</span><span class="value">{safe_code}</span></div>
                        <div class="detail-row"><span class="label">Status:</span><span class="value" style="color:#34D399;">AUTHENTIC</span></div>
                    </div>
                    <div class="footer">Issued and secured by Aereo Credential Engine</div>
                </div>
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
                <title>Invalid Certificate</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0F172A; color: #F8FAFC; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 16px; box-sizing: border-box; }}
                    .card {{ background: #1E293B; border: 1px solid #7F1D1D; border-radius: 16px; padding: 32px; max-width: 480px; width: 100%; text-align: center; }}
                    .badge {{ background: #7F1D1D; color: #F87171; font-weight: 700; font-size: 13px; padding: 6px 16px; border-radius: 9999px; display: inline-flex; margin-bottom: 24px; }}
                    h1 {{ font-size: 22px; color: #FCA5A5; margin-bottom: 12px; }}
                    p {{ color: #94A3B8; font-size: 14px; margin-bottom: 24px; }}
                    .code {{ font-family: monospace; background: #0F172A; padding: 8px; border-radius: 6px; color: #E2E8F0; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="badge">&#10007; VERIFICATION FAILED</div>
                    <h1>Certificate Not Found</h1>
                    <p>The code below does not correspond to an authentic issued certificate.</p>
                    <div class="code">{safe_invalid_code}</div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=invalid_html, status_code=404)

    # API / JSON response
    status_code = 200 if result.valid else 404
    return JSONResponse(content=result.model_dump(mode="json"), status_code=status_code)
