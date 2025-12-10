"""Financial Modeling Prep API client for fetching financial data."""

import requests
from typing import List, Dict, Optional

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPClient:
    def __init__(self, api_key: str):
        """
        Initialize FMP API client.

        Args:
            api_key: Your FMP API key
        """
        self.api_key = api_key
        self.base_url = BASE_URL

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a request to the FMP API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters

        Returns:
            Response JSON data
        """
        if params is None:
            params = {}

        params['apikey'] = self.api_key
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {endpoint}: {e}")
            return {}

    def get_balance_sheet(self, symbol: str, period: str = "annual", limit: int = 10) -> List[Dict]:
        """
        Fetch balance sheet data for a company.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            period: "annual" or "quarter"
            limit: Number of periods to fetch (default 10 years)

        Returns:
            List of balance sheet statements
        """
        endpoint = f"balance-sheet-statement/{symbol}"
        params = {
            'period': period,
            'limit': limit
        }
        result = self._make_request(endpoint, params)
        return result.get('financials', [])

    def get_company_profile(self, symbol: str) -> Dict:
        """
        Fetch company profile information.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Company profile data
        """
        endpoint = f"profile/{symbol}"
        result = self._make_request(endpoint)
        return result[0] if isinstance(result, list) and result else result

    def get_available_symbols(self, limit: int = 100) -> List[str]:
        """
        Get a list of available stock symbols.

        Args:
            limit: Number of symbols to fetch

        Returns:
            List of stock ticker symbols
        """
        endpoint = "available-traded/list"
        result = self._make_request(endpoint)
        symbols = result.get('symbolsList', [])[:limit]
        return [s.get('symbol') for s in symbols if s.get('symbol')]
