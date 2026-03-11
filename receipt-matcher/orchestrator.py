"""
Receipt Matcher – Orchestrator
================================
Phase 1 MVP entry point.

Workflow:
  1.  Index all Gmail accounts (skip if already done and --no-reindex)
  2.  Load Revolut CSV transactions
  3.  Match each transaction against the email index
  4.  Write results to matched.csv / unmatched.csv
  5.  Print a summary report

Usage:
  python orchestrator.py [--csv PATH] [--reindex] [--no-match] [-v]
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import config
from agents import email_indexer, transaction_agent, match_agent, output_agent

logger = logging.getLogger("orchestrator")


# ── CLI ────────────────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Receipt Matcher MVP – index emails and match Revolut transactions."
    )
    p.add_argument(
        "--csv", metavar="PATH",
        help="Path to Revolut CSV (default: first .csv in input/)"
    )
    p.add_argument(
        "--reindex", action="store_true",
        help="Force re-index all Gmail accounts even if already indexed"
    )
    p.add_argument(
        "--no-index", action="store_true",
        help="Skip email indexing (use existing ChromaDB)"
    )
    p.add_argument(
        "--no-match", action="store_true",
        help="Only index emails, skip matching"
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable DEBUG logging"
    )
    return p.parse_args()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s %(name)s – %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", stream=sys.stdout)
    # Quiet noisy libraries
    for noisy in ("urllib3", "google", "httplib2", "oauth2client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Steps ──────────────────────────────────────────────────────────────────────
def step_index(force: bool = False) -> int:
    """Index all configured Gmail accounts. Returns total docs indexed."""
    if not config.GMAIL_ACCOUNTS:
        logger.warning(
            "No Gmail accounts configured. "
            "Set GMAIL_ACCOUNTS=you@gmail.com in .env and re-run."
        )
        return 0

    stats_before = email_indexer.get_collection_stats()
    logger.info(
        "ChromaDB: %d documents already indexed.", stats_before["total_documents"]
    )

    if stats_before["total_documents"] > 0 and not force:
        logger.info(
            "Index not empty – skipping re-index (use --reindex to force)."
        )
        return 0

    logger.info("Starting email indexing for accounts: %s", config.GMAIL_ACCOUNTS)
    indexed = email_indexer.index_all_accounts(force_reindex=force)
    stats_after = email_indexer.get_collection_stats()
    logger.info(
        "Indexing complete. %d new documents | %d total in index.",
        indexed, stats_after["total_documents"]
    )
    return indexed


def step_load_transactions(csv_path: str | None) -> list:
    """Load and return transactions from the Revolut CSV."""
    transactions = transaction_agent.load_transactions(csv_path)
    if not transactions:
        logger.warning("No expense transactions found in CSV – nothing to match.")
    return transactions


def step_match(transactions: list) -> list:
    """Match all transactions and write output CSVs."""
    if not transactions:
        return []

    results = match_agent.match_all(transactions)

    # Build a lookup so we can pass the Transaction to the output agent
    tx_by_id = {t.id: t for t in transactions}

    for result in results:
        tx = tx_by_id[result.transaction_id]
        if result.status == "matched":
            output_agent.record_match(tx, result)
        else:
            output_agent.record_unmatched(tx, result)

    return results


# ── Report ─────────────────────────────────────────────────────────────────────
def _print_report(transactions: list, results: list) -> None:
    summary = output_agent.get_summary()
    print()
    print("=" * 60)
    print("  RECEIPT MATCHER – SUMMARY REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print(f"  Transactions processed : {len(transactions)}")
    print(f"  Matched                : {summary['matched']}  →  {config.MATCHED_CSV.name}")
    print(f"  Unmatched              : {summary['unmatched']}  →  {config.UNMATCHED_CSV.name}")
    print(f"  Match rate             : {summary['match_rate']}")
    print("=" * 60)

    if results:
        print()
        print("  UNMATCHED (manual review needed):")
        unmatched = [r for r in results if r.status == "unmatched"]
        if unmatched:
            for r in unmatched[:20]:
                tx_id_parts = r.transaction_id.split("_")
                date_part = tx_id_parts[0] if tx_id_parts else "?"
                amount_part = tx_id_parts[1] if len(tx_id_parts) > 1 else "?"
                print(f"    {date_part}  {amount_part:>10}  {r.reason[:50]}")
            if len(unmatched) > 20:
                print(f"    … and {len(unmatched) - 20} more (see {config.UNMATCHED_CSV.name})")
        else:
            print("    None – perfect match rate!")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    args = _parse_args()
    _setup_logging(args.verbose)

    logger.info("Receipt Matcher MVP starting …")
    logger.info("Project dir: %s", config.BASE_DIR)

    # Step 1 – Index
    if not args.no_index:
        step_index(force=args.reindex)
    else:
        stats = email_indexer.get_collection_stats()
        logger.info("Skipping indexing. Current index: %d docs", stats["total_documents"])

    if args.no_match:
        logger.info("--no-match set, exiting after indexing.")
        return 0

    # Step 2 – Load transactions
    try:
        transactions = step_load_transactions(args.csv)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except ValueError as exc:
        logger.error("CSV format error: %s", exc)
        return 1

    if not transactions:
        return 0

    # Step 3 – Match
    results = step_match(transactions)

    # Step 4 – Report
    _print_report(transactions, results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
