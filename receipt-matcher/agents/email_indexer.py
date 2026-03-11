"""
Agent 1 – Email Indexer Agent
==============================
* One-time: fetches all 2025 emails from every configured Gmail account
  and indexes them (with extracted metadata) into ChromaDB.
* Persistent (Phase 2): can be called for a single new message-id to
  incrementally update the index.

Extracted per email:
  - sender, date, subject
  - body text (plain/html stripped)
  - PDF attachment text
  - inferred: amount, currency, merchant
"""

import base64
import email as email_lib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

import config
from utils.gmail_auth import get_gmail_service
from utils.pdf_extractor import extract_text as extract_pdf_text

logger = logging.getLogger(__name__)

# ── ChromaDB setup ─────────────────────────────────────────────────────────────
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_NAME,
        embedding_function=_ef,
        metadata={"hnsw:space": "cosine"},
    )


# ── Amount / currency extraction ───────────────────────────────────────────────
_AMOUNT_RE = re.compile(
    r"(?:EUR|USD|GBP|CHF|€|\$|£)\s*(\d{1,6}(?:[.,]\d{1,2})?)"
    r"|(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:EUR|USD|GBP|CHF|€|\$|£)",
    re.IGNORECASE,
)
_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}


def _parse_amount(text: str) -> tuple[float | None, str | None]:
    """Return (amount_float, currency_code) from the first money pattern found."""
    for m in _AMOUNT_RE.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", ".")
        try:
            amount = float(raw)
        except ValueError:
            continue
        # Detect currency from surrounding context
        span_start = max(0, m.start() - 5)
        span_end = min(len(text), m.end() + 5)
        context = text[span_start:span_end]
        currency = "EUR"
        for sym, code in _CURRENCY_SYMBOLS.items():
            if sym in context:
                currency = code
                break
        for code in ("USD", "GBP", "CHF", "EUR"):
            if code in context.upper():
                currency = code
                break
        return amount, currency
    return None, None


# ── Gmail helpers ──────────────────────────────────────────────────────────────
def _decode_payload(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text (or html-stripped) body from a Gmail payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and body_data:
        return _decode_payload(body_data)

    if mime == "text/html" and body_data:
        html = _decode_payload(body_data)
        # Minimal tag stripping
        return re.sub(r"<[^>]+>", " ", html)

    parts = payload.get("parts", [])
    for part in parts:
        text = _extract_body(part)
        if text:
            return text
    return ""


def _extract_attachments(service, user_id: str, message_id: str, payload: dict) -> list[str]:
    """Download PDF attachments and return their extracted text."""
    texts: list[str] = []
    parts = payload.get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        if not filename.lower().endswith(".pdf"):
            continue
        att_id = part.get("body", {}).get("attachmentId")
        if not att_id:
            continue
        try:
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=message_id, id=att_id)
                .execute()
            )
            pdf_bytes = base64.urlsafe_b64decode(att["data"] + "==")
            tmp = config.DATA_DIR / f"_tmp_{message_id}_{filename}"
            tmp.write_bytes(pdf_bytes)
            text = extract_pdf_text(tmp)
            tmp.unlink(missing_ok=True)
            if text.strip():
                texts.append(f"[PDF: {filename}]\n{text}")
        except Exception as exc:
            logger.debug("Could not download attachment %s: %s", filename, exc)
    return texts


def _fetch_message(service, user_id: str, msg_id: str) -> dict[str, Any] | None:
    try:
        return service.users().messages().get(
            userId=user_id,
            id=msg_id,
            format="full",
        ).execute()
    except Exception as exc:
        logger.warning("Failed to fetch message %s: %s", msg_id, exc)
        return None


def _parse_message(service, user_id: str, raw_msg: dict) -> dict[str, Any] | None:
    """Parse a raw Gmail message into a structured receipt document."""
    headers = {h["name"].lower(): h["value"] for h in raw_msg.get("payload", {}).get("headers", [])}
    date_str = headers.get("date", "")
    sender = headers.get("from", "")
    subject = headers.get("subject", "")

    try:
        msg_date = email_lib.utils.parsedate_to_datetime(date_str)
    except Exception:
        msg_date = datetime.now(timezone.utc)

    # Only index emails from the configured year
    if msg_date.year != config.INDEX_YEAR:
        return None

    body = _extract_body(raw_msg.get("payload", {}))
    attachment_texts = _extract_attachments(service, user_id, raw_msg["id"], raw_msg.get("payload", {}))

    full_text = "\n".join([subject, sender, body] + attachment_texts)
    amount, currency = _parse_amount(full_text)

    return {
        "id": raw_msg["id"],
        "date": msg_date.isoformat(),
        "date_ts": int(msg_date.timestamp()),
        "sender": sender,
        "subject": subject,
        "body": body[:2000],          # cap to avoid oversized vectors
        "attachment_text": "\n".join(attachment_texts)[:3000],
        "amount": amount,
        "currency": currency,
        "full_text": full_text[:4000],
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def index_all_accounts(force_reindex: bool = False) -> int:
    """
    Index all emails from all configured Gmail accounts.
    Returns total number of newly indexed documents.
    """
    collection = _get_collection()
    total = 0
    for account in config.GMAIL_ACCOUNTS:
        logger.info("Indexing account: %s", account)
        count = _index_account(account, collection, force_reindex=force_reindex)
        logger.info("  → %d documents indexed for %s", count, account)
        total += count
    return total


def _index_account(email: str, collection: chromadb.Collection, force_reindex: bool = False) -> int:
    service = get_gmail_service(email)
    user_id = "me"

    # Query Gmail for all messages in the target year
    query = f"after:{config.INDEX_YEAR}/01/01 before:{config.INDEX_YEAR + 1}/01/01"
    logger.info("Gmail query: %s", query)

    msg_ids: list[str] = []
    page_token = None
    while True:
        kwargs: dict = {
            "userId": user_id,
            "q": query,
            "maxResults": 500,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        msgs = resp.get("messages", [])
        msg_ids.extend(m["id"] for m in msgs)
        page_token = resp.get("nextPageToken")
        if not page_token or len(msg_ids) >= config.MAX_EMAILS_PER_ACCOUNT:
            break

    logger.info("Found %d messages in %s for %s", len(msg_ids), config.INDEX_YEAR, email)

    # Filter already-indexed if not forcing
    if not force_reindex:
        existing = set(collection.get(ids=msg_ids[:100])["ids"]) if msg_ids else set()
        # For large sets, skip ids already present (sampled check)
        # Full dedup happens per-upsert below

    indexed = 0
    batch_docs: list[str] = []
    batch_metas: list[dict] = []
    batch_ids: list[str] = []
    BATCH_SIZE = 50

    for msg_id in tqdm(msg_ids, desc=f"Indexing {email}", unit="email"):
        raw = _fetch_message(service, user_id, msg_id)
        if not raw:
            continue
        doc = _parse_message(service, user_id, raw)
        if not doc:
            continue

        batch_ids.append(doc["id"])
        batch_docs.append(doc["full_text"])
        meta = {k: v for k, v in doc.items() if k != "full_text" and v is not None}
        # ChromaDB metadata values must be str/int/float/bool
        for k, v in list(meta.items()):
            if not isinstance(v, (str, int, float, bool)):
                meta[k] = str(v)
        batch_metas.append(meta)

        if len(batch_ids) >= BATCH_SIZE:
            collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
            indexed += len(batch_ids)
            batch_ids, batch_docs, batch_metas = [], [], []
            time.sleep(0.1)  # gentle rate limiting

    if batch_ids:
        collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
        indexed += len(batch_ids)

    return indexed


def index_single_message(email: str, message_id: str) -> bool:
    """
    Index a single Gmail message by ID (used for real-time push in Phase 2).
    Returns True if successfully indexed.
    """
    collection = _get_collection()
    service = get_gmail_service(email)
    raw = _fetch_message(service, "me", message_id)
    if not raw:
        return False
    doc = _parse_message(service, "me", raw)
    if not doc:
        return False
    collection.upsert(
        ids=[doc["id"]],
        documents=[doc["full_text"]],
        metadatas=[{k: v for k, v in doc.items() if k != "full_text" and v is not None}],
    )
    logger.info("Indexed single message %s from %s", message_id, email)
    return True


def get_collection_stats() -> dict:
    collection = _get_collection()
    return {
        "total_documents": collection.count(),
        "collection": config.CHROMA_COLLECTION_NAME,
    }
