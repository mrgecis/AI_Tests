"""
Agent 2 – Transaction Agent
============================
Reads a Revolut Business CSV export and returns a clean list of
Transaction objects.

Revolut Business CSV columns (as of 2024):
  Type, Product, Started Date, Completed Date, Description,
  Amount, Fee, Currency, State, Balance

The agent is tolerant of slightly different column orderings and
handles both comma-separated and semicolon-separated files.
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

import config

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    id: str                    # Synthetic: YYYY-MM-DD_<amount>_<idx>
    date: date
    completed_date: Optional[date]
    description: str
    merchant: str              # Cleaned merchant name
    amount: float              # Negative = debit (expense), positive = credit
    currency: str
    transaction_type: str      # CARD_PAYMENT, TRANSFER, etc.
    state: str                 # COMPLETED, PENDING, REVERTED, …
    raw: dict = field(default_factory=dict, repr=False)


# ── Column name normalisers ───────────────────────────────────────────────────
_COL_MAP = {
    # Revolut Business export (English)
    "type": "type",
    "product": "product",
    "started date": "started_date",
    "completed date": "completed_date",
    "description": "description",
    "amount": "amount",
    "fee": "fee",
    "currency": "currency",
    "state": "state",
    "balance": "balance",
    # Some exports use slightly different names
    "date": "started_date",
    "merchant": "description",
    "reference": "description",
    "transaction type": "type",
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {c: _COL_MAP[c] for c in df.columns if c in _COL_MAP}
    return df.rename(columns=rename)


def _parse_date(value: str) -> Optional[date]:
    if not value or str(value).strip() in ("", "nan"):
        return None
    value = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse date: %r", value)
    return None


def _clean_merchant(description: str) -> str:
    """
    Extract a clean merchant name from a Revolut description field.
    Examples:
      "Card payment to MARRIOTT HOTELS" → "Marriott Hotels"
      "Payment to LUFTHANSA 12345"      → "Lufthansa"
      "Amazon.de"                        → "Amazon.de"
    """
    desc = description.strip()
    # Strip leading prefixes
    for prefix in (
        "card payment to ",
        "payment to ",
        "purchase at ",
        "pos ",
    ):
        if desc.lower().startswith(prefix):
            desc = desc[len(prefix):]
            break

    # Remove trailing reference numbers (all-digit or mixed short codes)
    desc = re.sub(r"\s+\d{4,}\s*$", "", desc).strip()
    # Remove country codes at end: "MARRIOTT GB" → "Marriott"
    desc = re.sub(r"\s+[A-Z]{2}\s*$", "", desc).strip()

    # Title-case
    return desc.title()


def load_transactions(csv_path: Optional[str | Path] = None) -> list[Transaction]:
    """
    Load and parse a Revolut Business CSV file.

    If *csv_path* is None the function looks for the first .csv file
    found in config.INPUT_DIR.
    """
    if csv_path is None:
        csvs = list(config.INPUT_DIR.glob("*.csv"))
        if not csvs:
            raise FileNotFoundError(
                f"No CSV file found in {config.INPUT_DIR}. "
                "Please drop your Revolut export there."
            )
        csv_path = csvs[0]
        logger.info("Auto-detected CSV: %s", csv_path)

    csv_path = Path(csv_path)
    logger.info("Loading transactions from %s", csv_path.name)

    # Detect delimiter
    with open(csv_path, "r", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    df = pd.read_csv(csv_path, delimiter=delimiter, dtype=str)
    df = _normalise_columns(df)

    required = {"started_date", "amount", "currency"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    transactions: list[Transaction] = []
    for idx, row in df.iterrows():
        started = _parse_date(row.get("started_date", ""))
        completed = _parse_date(row.get("completed_date", ""))

        try:
            amount = float(str(row["amount"]).replace(",", "."))
        except ValueError:
            logger.warning("Row %d: could not parse amount %r – skipping", idx, row.get("amount"))
            continue

        currency = str(row.get("currency", "EUR")).strip().upper()
        description = str(row.get("description", "")).strip()
        state = str(row.get("state", "COMPLETED")).strip().upper()
        tx_type = str(row.get("type", "CARD_PAYMENT")).strip().upper()

        # Only match expense transactions (debits)
        if amount >= 0:
            continue
        if state in ("REVERTED", "DECLINED", "FAILED"):
            continue

        effective_date = completed or started
        if effective_date is None:
            logger.warning("Row %d: no parseable date – skipping", idx)
            continue

        tx_id = f"{effective_date.isoformat()}_{abs(amount):.2f}_{idx}"
        merchant = _clean_merchant(description) if description else "Unknown"

        transactions.append(
            Transaction(
                id=tx_id,
                date=effective_date,
                completed_date=completed,
                description=description,
                merchant=merchant,
                amount=abs(amount),   # store as positive expense amount
                currency=currency,
                transaction_type=tx_type,
                state=state,
                raw=row.to_dict(),
            )
        )

    logger.info("Loaded %d expense transactions from CSV", len(transactions))
    return transactions


def transactions_to_dict(txs: list[Transaction]) -> list[dict]:
    """Convert Transaction objects to plain dicts for serialisation."""
    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "merchant": t.merchant,
            "description": t.description,
            "amount": t.amount,
            "currency": t.currency,
            "type": t.transaction_type,
            "state": t.state,
        }
        for t in txs
    ]
