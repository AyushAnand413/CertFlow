import os
from io import BytesIO
from typing import Dict, Any, Optional

import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# Determine directory paths for bundled TrueType fonts
FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
NOTO_SANS_PATH = os.path.join(FONTS_DIR, "NotoSans-Regular.ttf")
NOTO_DEV_PATH = os.path.join(FONTS_DIR, "NotoSansDevanagari-Regular.ttf")

# Register TrueType fonts with ReportLab
FONT_LATIN = "Helvetica"
FONT_DEV = "Helvetica"

if os.path.isfile(NOTO_SANS_PATH):
    try:
        pdfmetrics.registerFont(TTFont("NotoSans", NOTO_SANS_PATH))
        FONT_LATIN = "NotoSans"
    except Exception as e:
        print(f"Warning: Failed to load NotoSans font: {e}")

if os.path.isfile(NOTO_DEV_PATH):
    try:
        pdfmetrics.registerFont(TTFont("NotoDevanagari", NOTO_DEV_PATH))
        FONT_DEV = "NotoDevanagari"
    except Exception as e:
        print(f"Warning: Failed to load NotoDevanagari font: {e}")


def is_devanagari(text: str) -> bool:
    """Return True if the text contains Devanagari (Hindi/Sanskrit) characters."""
    return any("\u0900" <= char <= "\u097F" for char in text)


def get_font_for_text(text: str) -> str:
    """Select the appropriate font based on language script detection."""
    if is_devanagari(text):
        return FONT_DEV
    return FONT_LATIN


def generate_qr_code_image(data: str) -> BytesIO:
    """Generate a clean QR code PNG in-memory stream."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def render_certificate(
    recipient_name: str,
    certificate_info: Dict[str, Any],
    verification_code: str,
    verification_base_url: str = "http://localhost:8000/verify",
) -> bytes:
    """
    Renders a single vector certificate to PDF bytes.
    Features:
    - Decorative dual-tone vector border (Navy & Gold)
    - Dynamic text scaling for long recipient names
    - Multi-language font detection (Latin vs Devanagari)
    - Verification QR code and Certificate ID
    """
    buffer = BytesIO()
    page_width, page_height = landscape(A4)  # 841.89 x 595.27 points
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    c.setTitle(f"Certificate - {recipient_name}")

    # Color Palette
    color_navy = colors.HexColor("#0F172A")       # Deep slate navy
    color_gold = colors.HexColor("#B45309")       # Rich amber gold
    color_gold_light = colors.HexColor("#FBBF24") # Bright gold
    color_subtle = colors.HexColor("#64748B")     # Slate grey
    color_text = colors.HexColor("#1E293B")       # Dark charcoal

    center_x = page_width / 2.0

    # 1. Background Tint
    c.setFillColor(colors.HexColor("#FAFAF9"))    # Warm stone background
    c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    # 2. Outer Border (Navy)
    c.setStrokeColor(color_navy)
    c.setLineWidth(3.0)
    c.rect(20, 20, page_width - 40, page_height - 40, fill=0, stroke=1)

    # 3. Inner Decorative Border (Gold)
    c.setStrokeColor(color_gold)
    c.setLineWidth(1.5)
    c.rect(28, 28, page_width - 56, page_height - 56, fill=0, stroke=1)

    # Corner Accents (Gold corner brackets)
    corner_size = 18
    c.setStrokeColor(color_gold)
    c.setLineWidth(2.5)
    # Top-Left
    c.line(24, page_height - 24, 24 + corner_size, page_height - 24)
    c.line(24, page_height - 24, 24, page_height - 24 - corner_size)
    # Top-Right
    c.line(page_width - 24, page_height - 24, page_width - 24 - corner_size, page_height - 24)
    c.line(page_width - 24, page_height - 24, page_width - 24, page_height - 24 - corner_size)
    # Bottom-Left
    c.line(24, 24, 24 + corner_size, 24)
    c.line(24, 24, 24, 24 + corner_size)
    # Bottom-Right
    c.line(page_width - 24, 24, page_width - 24 - corner_size, 24)
    c.line(page_width - 24, 24, page_width - 24, 24 + corner_size)

    # 4. Header Badge / Top Accent
    c.setFillColor(color_gold)
    c.circle(center_x, page_height - 65, 12, fill=1, stroke=0)
    c.setFillColor(color_gold_light)
    c.circle(center_x, page_height - 65, 8, fill=1, stroke=0)
    c.setStrokeColor(color_gold)
    c.setLineWidth(1)
    c.line(center_x - 120, page_height - 65, center_x - 22, page_height - 65)
    c.line(center_x + 22, page_height - 65, center_x + 120, page_height - 65)

    # 5. Certificate Title
    title = str(certificate_info.get("title", "CERTIFICATE OF ACHIEVEMENT")).upper()
    title_font = get_font_for_text(title)
    c.setFont(title_font, 26)
    c.setFillColor(color_navy)
    c.drawCentredString(center_x, page_height - 110, title)

    # 6. Presentation Line
    c.setFont(FONT_LATIN, 11)
    c.setFillColor(color_subtle)
    c.drawCentredString(center_x, page_height - 150, "THIS CERTIFICATE IS PROUDLY PRESENTED TO")

    # 7. Recipient Name (with dynamic font sizing & script selection)
    name = recipient_name.strip()
    name_font = get_font_for_text(name)
    max_name_width = page_width - 180  # Safe bounds between borders

    # Dynamic scaling for long recipient names
    font_size = 34
    while font_size > 14:
        text_width = c.stringWidth(name, name_font, font_size)
        if text_width <= max_name_width:
            break
        font_size -= 2

    c.setFont(name_font, font_size)
    c.setFillColor(color_navy)
    name_y = page_height - 210
    c.drawCentredString(center_x, name_y, name)

    # Decorative Underline for Name
    c.setStrokeColor(color_gold)
    c.setLineWidth(1.5)
    underline_width = min(max(c.stringWidth(name, name_font, font_size) + 40, 240), max_name_width)
    c.line(center_x - (underline_width / 2.0), name_y - 12, center_x + (underline_width / 2.0), name_y - 12)

    # 8. Achievement / Event Description
    event_name = str(certificate_info.get("event_name", certificate_info.get("course_name", "the training program")))
    c.setFont(FONT_LATIN, 12)
    c.setFillColor(color_subtle)
    c.drawCentredString(center_x, page_height - 265, "for successfully completing")

    event_font = get_font_for_text(event_name)
    c.setFont(event_font, 17)
    c.setFillColor(color_navy)
    c.drawCentredString(center_x, page_height - 295, event_name)

    # Optional description / extra text
    description = certificate_info.get("description")
    if description:
        desc_font = get_font_for_text(description)
        c.setFont(desc_font, 10)
        c.setFillColor(color_subtle)
        c.drawCentredString(center_x, page_height - 325, str(description))

    # 9. Footer: Issue Date (Left)
    issue_date = str(certificate_info.get("issue_date", "October 9, 2026"))
    left_x = 140
    c.setStrokeColor(color_subtle)
    c.setLineWidth(1)
    c.line(left_x - 70, 115, left_x + 70, 115)
    c.setFont(FONT_LATIN, 10)
    c.setFillColor(color_text)
    c.drawCentredString(left_x, 95, issue_date)
    c.setFont(FONT_LATIN, 8)
    c.setFillColor(color_subtle)
    c.drawCentredString(left_x, 82, "DATE OF ISSUE")

    # 10. Footer: Issuer / Authority (Center)
    issuer = str(certificate_info.get("issuer", "CertFlow Authority"))
    c.setStrokeColor(color_subtle)
    c.setLineWidth(1)
    c.line(center_x - 80, 115, center_x + 80, 115)
    issuer_font = get_font_for_text(issuer)
    c.setFont(issuer_font, 11)
    c.setFillColor(color_text)
    c.drawCentredString(center_x, 95, issuer)
    c.setFont(FONT_LATIN, 8)
    c.setFillColor(color_subtle)
    c.drawCentredString(center_x, 82, "AUTHORIZED SIGNATURE")

    # 11. Footer: Verification QR Code & ID (Right)
    qr_url = f"{verification_base_url.rstrip('/')}/{verification_code}"
    qr_stream = generate_qr_code_image(qr_url)
    qr_image = ImageReader(qr_stream)

    qr_size = 62
    qr_x = page_width - 170
    qr_y = 70
    c.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)

    # Verification Code below/beside QR
    c.setFont(FONT_LATIN, 7)
    c.setFillColor(color_subtle)
    c.drawCentredString(qr_x + (qr_size / 2.0), qr_y - 10, f"ID: {verification_code}")
    c.drawCentredString(qr_x + (qr_size / 2.0), qr_y - 20, "Scan to verify")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
