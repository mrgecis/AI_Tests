"""
PDF text extraction utilities.

Tries pdfplumber first (better layout handling), falls back to PyPDF2.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(pdf_path: str | Path) -> str:
    """Return the full text content of a PDF file."""
    path = Path(pdf_path)
    text = _extract_pdfplumber(path)
    if not text.strip():
        text = _extract_pypdf2(path)
    return text


def _extract_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(str(path)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception as exc:
        logger.debug("pdfplumber failed for %s: %s", path.name, exc)
        return ""


def _extract_pypdf2(path: Path) -> str:
    try:
        import PyPDF2  # noqa: PLC0415

        with open(path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception as exc:
        logger.debug("PyPDF2 failed for %s: %s", path.name, exc)
        return ""
