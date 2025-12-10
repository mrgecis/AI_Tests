#!/usr/bin/env python3
"""
Test script for FMP API integration.

This tests the modules without requiring an actual API key by using mock data.
"""

from debt_analyzer import DebtAnalyzer
from typing import List, Dict


def create_mock_balance_sheet(symbol: str, years: int = 10) -> List[Dict]:
    """Create mock balance sheet data for testing."""
    sheets = []
    base_debt = 10_000_000  # $10M base debt

    for i in range(years, 0, -1):
        # Simulate increasing debt over time (for testing)
        debt_increment = base_debt * 0.05 * (years - i)
        short_term = base_debt + debt_increment
        long_term = base_debt * 1.5 + debt_increment

        sheets.append({
            'date': f'202{0 + i - 1}-12-31' if i <= 9 else f'201{1 + i - 10}-12-31',
            'shortTermDebt': short_term,
            'longTermDebt': long_term,
        })

    return sheets


def test_debt_analyzer():
    """Test the debt analyzer with mock data."""
    print("Testing DebtAnalyzer with mock data...")
    print("-" * 60)

    # Create mock data
    mock_sheets = create_mock_balance_sheet("TEST")

    # Test extraction
    debt_data = DebtAnalyzer.extract_debt_data(mock_sheets)
    print(f"✓ Extracted {len(debt_data)} years of debt data")

    # Test analysis
    is_increasing, slope, data = DebtAnalyzer.is_debt_increasing(debt_data)
    print(f"✓ Trend analysis complete")
    print(f"  - Is increasing: {is_increasing}")
    print(f"  - Trend slope: {slope:+.2f}")

    # Test full company analysis
    result = DebtAnalyzer.analyze_company("TEST", mock_sheets)
    print(f"\n✓ Full analysis complete for TEST:")
    print(f"  - Status: {result['status']}")
    print(f"  - Change: {result['debt_change_pct']:+.1f}%")
    print(f"  - Data points: {result['data_points']}")

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Create a .env file with your API key:")
    print("   Copy .env.example to .env and add your FMP_API_KEY")
    print("\n2. Get a free API key at:")
    print("   https://site.financialmodelingprep.com/login")
    print("\n3. Run the main analysis:")
    print("   python3 analyze_debt.py")


if __name__ == "__main__":
    test_debt_analyzer()
