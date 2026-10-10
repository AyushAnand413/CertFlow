import os
import pytest
from app.rendering.template import render_certificate, is_devanagari
from app.storage.local import LocalStorage


@pytest.fixture
def temp_storage(tmp_path):
    """Fixture providing an isolated temporary storage instance."""
    return LocalStorage(str(tmp_path))


@pytest.fixture
def sample_cert_info():
    """Fixture providing sample certificate metadata."""
    return {
        "title": "Certificate of Completion",
        "event_name": "Full Stack Backend Bootcamp",
        "issuer": "Tech Institute",
        "issue_date": "2026-10-09",
        "description": "Demonstrated mastery of distributed queues and API design.",
    }


def test_is_devanagari_detection():
    """Verify script detection correctly identifies Devanagari vs Latin characters."""
    assert is_devanagari("आयुष आनंद") is True
    assert is_devanagari("राहुल शर्मा") is True
    assert is_devanagari("Ayush Anand") is False
    assert is_devanagari("René Müller") is False
    assert is_devanagari("John Doe 123") is False


def test_render_english_certificate(sample_cert_info):
    """Verify that an English recipient generates a valid non-empty PDF byte stream."""
    pdf_bytes = render_certificate(
        recipient_name="Ayush Anand",
        certificate_info=sample_cert_info,
        verification_code="CERT-EN-101",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    # Standard PDF header signature
    assert pdf_bytes.startswith(b"%PDF-")


def test_render_hindi_certificate(sample_cert_info):
    """Verify that a Hindi recipient renders without UnicodeEncodeError and creates a valid PDF."""
    pdf_bytes = render_certificate(
        recipient_name="आयुष आनंद",
        certificate_info=sample_cert_info,
        verification_code="CERT-HI-202",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")


def test_render_long_name_scaling(sample_cert_info):
    """Verify that very long names scale down font size gracefully without errors."""
    long_name = "Dr. Bartholomew Alexander Montgomery-Fitzgerald III of Edinburgh"
    pdf_bytes = render_certificate(
        recipient_name=long_name,
        certificate_info=sample_cert_info,
        verification_code="CERT-LONG-303",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_storage_lifecycle(temp_storage, sample_cert_info):
    """Verify storage save, exists, get_size, open, and delete operations."""
    pdf_bytes = render_certificate(
        recipient_name="Test User",
        certificate_info=sample_cert_info,
        verification_code="CERT-STORAGE-404",
    )
    rel_path = "certs/CERT-STORAGE-404.pdf"

    # 1. Save
    saved_path = temp_storage.save(rel_path, pdf_bytes)
    assert saved_path == rel_path
    assert temp_storage.exists(rel_path) is True

    # 2. Check size
    size = temp_storage.get_size(rel_path)
    assert size == len(pdf_bytes)

    # 3. Read stream
    with temp_storage.open(rel_path) as f:
        read_bytes = f.read()
        assert read_bytes == pdf_bytes

    # 4. Delete
    deleted = temp_storage.delete(rel_path)
    assert deleted is True
    assert temp_storage.exists(rel_path) is False
