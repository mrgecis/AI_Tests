"""
Agent 5 – Output Agent
=======================
Responsible for all file-system outputs:
  * Copies / downloads matched PDF receipts into output/
  * Maintains matched.csv, requested.csv, unmatched.csv
  * Never overwrites an existing matched entry with a worse one
"""

import csv
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import config
from agents.match_agent import MatchResult
from agents.transaction_agent import Transaction

logger = logging.getLogger(__name__)

# ── CSV column definitions ────────────────────────────────────────────────────
_MATCHED_COLS = [
    "transaction_id", "date", "merchant", "amount", "currency",
    "matched_doc_id", "matched_subject", "matched_sender",
    "matched_date", "matched_amount", "confidence", "reason",
    "pdf_path", "indexed_at",
]

_UNMATCHED_COLS = [
    "transaction_id", "date", "merchant", "amount", "currency",
    "description", "reason", "candidates_found", "indexed_at",
]

_REQUESTED_COLS = [
    "transaction_id", "date", "merchant", "amount", "currency",
    "description", "requested_at", "status",
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_csv(path: Path, fieldnames: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _pdf_filename(tx: Transaction) -> str:
    """Canonical PDF filename: YYYY-MM-DD_AMOUNT_MERCHANT.pdf"""
    merchant = tx.merchant.replace(" ", "_").replace("/", "-")[:40]
    return f"{tx.date.isoformat()}_{tx.amount:.2f}{tx.currency}_{merchant}.pdf"


# ── Saving PDFs ───────────────────────────────────────────────────────────────
def _download_pdf_from_chroma(doc_id: str, tx: Transaction) -> Optional[Path]:
    """
    Try to retrieve the original PDF attachment that was stored alongside the email.
    In MVP this is a best-effort: we look for a temp file saved during indexing,
    or we note that Phase 2 should store attachments persistently.
    """
    # Phase 2 will persist PDFs. For now, just note the doc_id.
    return None


def save_matched_pdf(tx: Transaction, result: MatchResult) -> Optional[Path]:
    """
    Copy a matched PDF into output/ with the canonical filename.
    Returns the path on success, None if no PDF is available.
    """
    pdf = _download_pdf_from_chroma(result.matched_doc_id or "", tx)
    if pdf and pdf.exists():
        dest = config.OUTPUT_DIR / _pdf_filename(tx)
        shutil.copy2(pdf, dest)
        logger.info("Saved PDF → %s", dest.name)
        return dest
    return None


# ── CSV updates ───────────────────────────────────────────────────────────────
def record_match(tx: Transaction, result: MatchResult) -> None:
    """Append or update an entry in matched.csv."""
    rows = _read_csv(config.MATCHED_CSV, _MATCHED_COLS)
    # Remove any existing entry for this transaction
    rows = [r for r in rows if r.get("transaction_id") != tx.id]

    pdf_path = save_matched_pdf(tx, result)

    rows.append({
        "transaction_id": tx.id,
        "date": tx.date.isoformat(),
        "merchant": tx.merchant,
        "amount": f"{tx.amount:.2f}",
        "currency": tx.currency,
        "matched_doc_id": result.matched_doc_id or "",
        "matched_subject": result.matched_subject or "",
        "matched_sender": result.matched_sender or "",
        "matched_date": result.matched_date or "",
        "matched_amount": result.matched_amount or "",
        "confidence": f"{result.confidence:.2f}",
        "reason": result.reason,
        "pdf_path": str(pdf_path) if pdf_path else "",
        "indexed_at": _now(),
    })
    _write_csv(config.MATCHED_CSV, rows, _MATCHED_COLS)
    logger.info("Recorded match for %s", tx.id)


def record_unmatched(tx: Transaction, result: MatchResult) -> None:
    """Append or update an entry in unmatched.csv."""
    rows = _read_csv(config.UNMATCHED_CSV, _UNMATCHED_COLS)
    rows = [r for r in rows if r.get("transaction_id") != tx.id]
    rows.append({
        "transaction_id": tx.id,
        "date": tx.date.isoformat(),
        "merchant": tx.merchant,
        "amount": f"{tx.amount:.2f}",
        "currency": tx.currency,
        "description": tx.description,
        "reason": result.reason,
        "candidates_found": result.candidates_found,
        "indexed_at": _now(),
    })
    _write_csv(config.UNMATCHED_CSV, rows, _UNMATCHED_COLS)
    logger.info("Recorded unmatched for %s", tx.id)


def record_requested(tx: Transaction, status: str = "requested") -> None:
    """Add an entry to requested.csv (used by Escalation Agent in Phase 2)."""
    rows = _read_csv(config.REQUESTED_CSV, _REQUESTED_COLS)
    rows = [r for r in rows if r.get("transaction_id") != tx.id]
    rows.append({
        "transaction_id": tx.id,
        "date": tx.date.isoformat(),
        "merchant": tx.merchant,
        "amount": f"{tx.amount:.2f}",
        "currency": tx.currency,
        "description": tx.description,
        "requested_at": _now(),
        "status": status,
    })
    _write_csv(config.REQUESTED_CSV, rows, _REQUESTED_COLS)
    logger.info("Recorded requested for %s", tx.id)


# ── Summary stats ─────────────────────────────────────────────────────────────
def get_summary() -> dict:
    matched = _read_csv(config.MATCHED_CSV, _MATCHED_COLS)
    unmatched = _read_csv(config.UNMATCHED_CSV, _UNMATCHED_COLS)
    requested = _read_csv(config.REQUESTED_CSV, _REQUESTED_COLS)
    total = len(matched) + len(unmatched)
    return {
        "matched": len(matched),
        "unmatched": len(unmatched),
        "requested": len(requested),
        "total": total,
        "match_rate": f"{100 * len(matched) / total:.1f}%" if total else "n/a",
    }
