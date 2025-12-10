#!/usr/bin/env python3
"""
Main script to analyze company debt trends using Financial Modeling Prep API.

This script fetches balance sheet data for multiple companies and identifies
those with increasing debt over time.
"""

import os
import sys
from typing import List
from dotenv import load_dotenv
from fmp_api import FMPClient
from debt_analyzer import DebtAnalyzer


def load_api_key() -> str:
    """Load API key from environment."""
    load_dotenv()
    api_key = os.getenv('FMP_API_KEY')

    if not api_key:
        print("Error: FMP_API_KEY not found in environment.")
        print("Please create a .env file with your API key:")
        print("  FMP_API_KEY=your_api_key_here")
        print("\nGet a free API key at: https://site.financialmodelingprep.com/login")
        sys.exit(1)

    return api_key


def analyze_companies(client: FMPClient, symbols: List[str]) -> tuple:
    """
    Analyze a list of companies for debt trends.

    Args:
        client: FMPClient instance
        symbols: List of stock ticker symbols

    Returns:
        Tuple of (increasing_debt_companies, decreasing_debt_companies)
    """
    increasing = []
    decreasing = []

    for symbol in symbols:
        print(f"Analyzing {symbol}...", end=" ", flush=True)

        balance_sheets = client.get_balance_sheet(symbol, period="annual", limit=10)

        if not balance_sheets:
            print("No data")
            continue

        result = DebtAnalyzer.analyze_company(symbol, balance_sheets)

        if result['status'] == 'no_data':
            print("No debt data")
            continue

        if result['is_increasing']:
            increasing.append(result)
            print("✓ Increasing debt")
        else:
            decreasing.append(result)
            print("✓ Decreasing debt")

    return increasing, decreasing


def format_currency(value: float) -> str:
    """Format a number as currency."""
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    elif abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    else:
        return f"${value:,.0f}"


def print_results(increasing: List[dict], decreasing: List[dict]):
    """Print analysis results in a readable format."""
    print("\n" + "=" * 80)
    print("DEBT TREND ANALYSIS RESULTS")
    print("=" * 80)

    # Companies with increasing debt
    print(f"\n📈 COMPANIES WITH INCREASING DEBT ({len(increasing)})")
    print("-" * 80)

    if increasing:
        for result in sorted(increasing, key=lambda x: x['debt_change_pct'], reverse=True):
            symbol = result['symbol']
            change_pct = result['debt_change_pct']
            earliest_debt = format_currency(result['earliest_debt'])
            latest_debt = format_currency(result['latest_debt'])
            earliest_date = result['earliest_date']
            latest_date = result['latest_date']

            print(f"\n{symbol}")
            print(f"  Period: {earliest_date} to {latest_date} ({result['data_points']} years)")
            print(f"  Debt increased by {change_pct:+.1f}%")
            print(f"  {earliest_date}: {earliest_debt}")
            print(f"  {latest_date}: {latest_debt}")
            print(f"  Trend slope: {result['trend_slope']:+.0f}")
    else:
        print("  No companies found with increasing debt.")

    # Companies with decreasing debt
    print(f"\n\n📉 COMPANIES WITH DECREASING DEBT ({len(decreasing)})")
    print("-" * 80)

    if decreasing:
        for result in sorted(decreasing, key=lambda x: x['debt_change_pct']):
            symbol = result['symbol']
            change_pct = result['debt_change_pct']
            earliest_debt = format_currency(result['earliest_debt'])
            latest_debt = format_currency(result['latest_debt'])
            earliest_date = result['earliest_date']
            latest_date = result['latest_date']

            print(f"\n{symbol}")
            print(f"  Period: {earliest_date} to {latest_date} ({result['data_points']} years)")
            print(f"  Debt changed by {change_pct:+.1f}%")
            print(f"  {earliest_date}: {earliest_debt}")
            print(f"  {latest_date}: {latest_debt}")
            print(f"  Trend slope: {result['trend_slope']:+.0f}")
    else:
        print("  No companies found with decreasing debt.")

    print("\n" + "=" * 80)


def main():
    """Main entry point."""
    api_key = load_api_key()
    client = FMPClient(api_key)

    # Example: Analyze major tech companies
    # You can modify this list or fetch symbols dynamically
    symbols = [
        "AAPL",  # Apple
        "MSFT",  # Microsoft
        "GOOGL", # Alphabet
        "AMZN",  # Amazon
        "TSLA",  # Tesla
        "META",  # Meta
        "NVDA",  # Nvidia
        "JPM",   # JPMorgan Chase
        "BAC",   # Bank of America
        "WMT",   # Walmart
    ]

    print(f"Analyzing {len(symbols)} companies...")
    print("-" * 80)

    increasing, decreasing = analyze_companies(client, symbols)

    print_results(increasing, decreasing)


if __name__ == "__main__":
    main()
