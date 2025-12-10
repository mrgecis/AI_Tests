"""Analyze balance sheet data to identify companies with increasing debt."""

from typing import List, Dict, Tuple
from datetime import datetime


class DebtAnalyzer:
    """Analyze debt trends from balance sheet data."""

    @staticmethod
    def extract_debt_data(balance_sheets: List[Dict]) -> List[Tuple[str, float]]:
        """
        Extract total debt from balance sheet data.

        Args:
            balance_sheets: List of balance sheet statements

        Returns:
            List of tuples (date, total_debt) sorted by date ascending
        """
        debt_data = []

        for sheet in balance_sheets:
            date = sheet.get('date')
            # Total debt = short-term debt + long-term debt
            short_term_debt = sheet.get('shortTermDebt') or 0
            long_term_debt = sheet.get('longTermDebt') or 0
            total_debt = short_term_debt + long_term_debt

            if total_debt > 0:  # Only include if debt exists
                debt_data.append((date, total_debt))

        # Sort by date ascending (oldest to newest)
        debt_data.sort(key=lambda x: x[0])
        return debt_data

    @staticmethod
    def is_debt_increasing(debt_data: List[Tuple[str, float]]) -> Tuple[bool, float, List[Tuple[str, float]]]:
        """
        Determine if debt is increasing over time.

        Uses linear regression to assess overall trend. A company is considered
        to have increasing debt if the trend slope is positive.

        Args:
            debt_data: List of tuples (date, total_debt) sorted by date

        Returns:
            Tuple of (is_increasing, trend_slope, debt_data)
        """
        if len(debt_data) < 2:
            return False, 0.0, debt_data

        # Simple linear regression to find trend
        n = len(debt_data)
        x_values = list(range(n))  # Use index as x (0, 1, 2, ...)
        y_values = [debt for _, debt in debt_data]

        # Calculate means
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        # Calculate slope
        numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        is_increasing = slope > 0
        return is_increasing, slope, debt_data

    @staticmethod
    def analyze_company(symbol: str, balance_sheets: List[Dict]) -> Dict:
        """
        Analyze a single company's debt trajectory.

        Args:
            symbol: Stock ticker symbol
            balance_sheets: List of balance sheet statements

        Returns:
            Dictionary with analysis results
        """
        debt_data = DebtAnalyzer.extract_debt_data(balance_sheets)

        if not debt_data:
            return {
                'symbol': symbol,
                'status': 'no_data',
                'message': 'No debt data available'
            }

        is_increasing, slope, data = DebtAnalyzer.is_debt_increasing(debt_data)

        # Calculate statistics
        earliest_date, earliest_debt = data[0]
        latest_date, latest_debt = data[-1]
        debt_change = latest_debt - earliest_debt
        debt_change_pct = (debt_change / earliest_debt * 100) if earliest_debt > 0 else 0
        avg_debt = sum(d for _, d in data) / len(data)

        return {
            'symbol': symbol,
            'status': 'increasing' if is_increasing else 'decreasing',
            'is_increasing': is_increasing,
            'trend_slope': slope,
            'earliest_date': earliest_date,
            'earliest_debt': earliest_debt,
            'latest_date': latest_date,
            'latest_debt': latest_debt,
            'debt_change': debt_change,
            'debt_change_pct': debt_change_pct,
            'average_debt': avg_debt,
            'data_points': len(data),
            'debt_data': data
        }
