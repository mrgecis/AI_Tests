"""
Agent 3 – Match Agent
======================
For each Transaction, this agent:
  1. Builds a semantic query and retrieves candidate emails from ChromaDB.
  2. Applies hard filters: amount (±1%), date (±3 days), merchant (fuzzy).
  3. If any candidates survive, asks Claude to confirm the best match.
  4. Returns a MatchResult with a confidence score and matched document.

Design principle: when in doubt, prefer unmatched over wrong match.
"""

import logging
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import anthropic
import chromadb
from chromadb.utils import embedding_functions
from thefuzz import fuzz

import config
from agents.transaction_agent import Transaction

logger = logging.getLogger(__name__)

# ── ChromaDB ──────────────────────────────────────────────────────────────────
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


# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class MatchResult:
    transaction_id: str
    status: str               # "matched" | "unmatched"
    confidence: float         # 0.0 – 1.0
    matched_doc_id: Optional[str] = None
    matched_subject: Optional[str] = None
    matched_sender: Optional[str] = None
    matched_date: Optional[str] = None
    matched_amount: Optional[float] = None
    matched_currency: Optional[str] = None
    reason: str = ""
    candidates_found: int = 0
    raw_candidates: list[dict] = field(default_factory=list, repr=False)


# ── Filtering helpers ──────────────────────────────────────────────────────────
def _amount_ok(tx_amount: float, doc_amount: Optional[float]) -> bool:
    if doc_amount is None:
        return True   # no amount extracted → don't filter out, let Claude decide
    tolerance = max(0.02, tx_amount * config.AMOUNT_TOLERANCE_PCT)
    return abs(tx_amount - doc_amount) <= tolerance


def _date_ok(tx_date: date, doc_date_str: Optional[str]) -> bool:
    if not doc_date_str:
        return True   # no date → don't filter, let Claude decide
    try:
        doc_date = date.fromisoformat(doc_date_str[:10])
        return abs((tx_date - doc_date).days) <= config.DATE_TOLERANCE_DAYS
    except ValueError:
        return True


def _merchant_score(tx_merchant: str, doc_sender: str, doc_subject: str) -> int:
    """Return the best fuzzy match score (0-100) between merchant and email metadata."""
    targets = [doc_sender, doc_subject]
    scores = [fuzz.partial_ratio(tx_merchant.lower(), t.lower()) for t in targets if t]
    return max(scores) if scores else 0


# ── Semantic search ────────────────────────────────────────────────────────────
def _build_query(tx: Transaction) -> str:
    return (
        f"Receipt invoice bill for {tx.merchant} "
        f"amount {tx.amount:.2f} {tx.currency} "
        f"date {tx.date.isoformat()}"
    )


def _retrieve_candidates(tx: Transaction, collection: chromadb.Collection, n: int = 10) -> list[dict]:
    query = _build_query(tx)
    try:
        results = collection.query(query_texts=[query], n_results=min(n, collection.count()))
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return []

    candidates = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        candidates.append({
            "id": doc_id,
            "document": docs[i] if i < len(docs) else "",
            "distance": distances[i] if i < len(distances) else 1.0,
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "date": meta.get("date", ""),
            "amount": meta.get("amount"),
            "currency": meta.get("currency", ""),
        })
    return candidates


# ── Hard filter pass ───────────────────────────────────────────────────────────
def _apply_hard_filters(tx: Transaction, candidates: list[dict]) -> list[dict]:
    filtered = []
    for c in candidates:
        amount_ok = _amount_ok(tx.amount, c.get("amount"))
        date_ok = _date_ok(tx.date, c.get("date"))
        merchant_score = _merchant_score(tx.merchant, c.get("sender", ""), c.get("subject", ""))
        merchant_ok = merchant_score >= config.MERCHANT_FUZZY_THRESHOLD

        logger.debug(
            "Candidate %s | amount_ok=%s date_ok=%s merchant_score=%d",
            c["id"][:8], amount_ok, date_ok, merchant_score,
        )

        # At least two of three criteria must pass (soft AND)
        passed = sum([amount_ok, date_ok, merchant_ok])
        if passed >= 2:
            c["merchant_score"] = merchant_score
            filtered.append(c)

    return filtered


# ── Claude confirmation ────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are a receipt-matching assistant.
Given a bank transaction and a list of email candidates, decide which email
(if any) is the matching receipt/invoice.

Rules:
- Amount must match within 1 % (consider rounding, different currencies only if conversion is obvious).
- Date must be within 3 calendar days.
- Merchant name must clearly refer to the same company (abbreviations, aliases OK).
- If no candidate clearly matches ALL three criteria, output status "unmatched".
- Never guess. Conservative matches are safer than wrong ones.

Respond ONLY with valid JSON:
{
  "status": "matched" | "unmatched",
  "matched_id": "<doc_id or null>",
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence>"
}
"""


def _ask_claude(tx: Transaction, candidates: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    tx_block = (
        f"Transaction:\n"
        f"  Merchant : {tx.merchant}\n"
        f"  Amount   : {tx.amount:.2f} {tx.currency}\n"
        f"  Date     : {tx.date.isoformat()}\n"
        f"  Description: {tx.description}\n"
    )

    cand_lines = []
    for c in candidates[:5]:   # limit to top-5 to stay within context
        cand_lines.append(
            f"- id={c['id'][:12]} | from={c['sender'][:60]} | "
            f"subject={c['subject'][:80]} | date={c['date'][:10]} | "
            f"amount={c['amount']} {c['currency']}"
        )
    cand_block = "Candidates:\n" + "\n".join(cand_lines)

    user_msg = f"{tx_block}\n{cand_block}"

    try:
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Claude call failed: %s", exc)
        return {"status": "unmatched", "matched_id": None, "confidence": 0.0, "reason": str(exc)}


# ── Public API ────────────────────────────────────────────────────────────────
def match_transaction(tx: Transaction) -> MatchResult:
    """
    Attempt to find a matching receipt email for *tx*.
    Returns a MatchResult (status is "matched" or "unmatched").
    """
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("ChromaDB collection is empty – run email indexer first.")
        return MatchResult(
            transaction_id=tx.id,
            status="unmatched",
            confidence=0.0,
            reason="Email index is empty.",
        )

    candidates = _retrieve_candidates(tx, collection)
    if not candidates:
        return MatchResult(
            transaction_id=tx.id,
            status="unmatched",
            confidence=0.0,
            reason="No semantic candidates found.",
        )

    filtered = _apply_hard_filters(tx, candidates)
    logger.info(
        "Transaction %s: %d candidates → %d after hard filters",
        tx.id, len(candidates), len(filtered),
    )

    if not filtered:
        return MatchResult(
            transaction_id=tx.id,
            status="unmatched",
            confidence=0.0,
            reason="No candidates passed amount/date/merchant filters.",
            candidates_found=len(candidates),
        )

    # Use Claude to pick the best match from filtered candidates
    verdict = _ask_claude(tx, filtered)

    if verdict.get("status") != "matched" or not verdict.get("matched_id"):
        return MatchResult(
            transaction_id=tx.id,
            status="unmatched",
            confidence=verdict.get("confidence", 0.0),
            reason=verdict.get("reason", "Claude found no match."),
            candidates_found=len(filtered),
            raw_candidates=filtered,
        )

    confidence = float(verdict.get("confidence", 0.0))
    if confidence < config.MATCH_CONFIDENCE_THRESHOLD:
        return MatchResult(
            transaction_id=tx.id,
            status="unmatched",
            confidence=confidence,
            reason=f"Confidence {confidence:.0%} below threshold. {verdict.get('reason', '')}",
            candidates_found=len(filtered),
            raw_candidates=filtered,
        )

    # Find the matched candidate's metadata
    matched_id = verdict["matched_id"]
    matched_cand = next((c for c in filtered if c["id"].startswith(matched_id[:12])), None)
    if matched_cand is None:
        matched_cand = filtered[0]

    return MatchResult(
        transaction_id=tx.id,
        status="matched",
        confidence=confidence,
        matched_doc_id=matched_cand["id"],
        matched_subject=matched_cand.get("subject"),
        matched_sender=matched_cand.get("sender"),
        matched_date=matched_cand.get("date", "")[:10],
        matched_amount=matched_cand.get("amount"),
        matched_currency=matched_cand.get("currency"),
        reason=verdict.get("reason", ""),
        candidates_found=len(filtered),
        raw_candidates=filtered,
    )


def match_all(transactions: list[Transaction]) -> list[MatchResult]:
    """Match a list of transactions, logging progress."""
    results = []
    total = len(transactions)
    matched_count = 0
    for i, tx in enumerate(transactions, 1):
        logger.info("[%d/%d] Matching: %s | %.2f %s | %s",
                    i, total, tx.merchant, tx.amount, tx.currency, tx.date)
        result = match_transaction(tx)
        if result.status == "matched":
            matched_count += 1
            logger.info("  ✓ MATCHED (%.0f%%) → %s", result.confidence * 100, result.matched_subject)
        else:
            logger.info("  ✗ UNMATCHED – %s", result.reason)
        results.append(result)

    logger.info("Done: %d/%d matched (%.0f%%)", matched_count, total,
                100 * matched_count / total if total else 0)
    return results
