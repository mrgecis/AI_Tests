"""Claude-powered chatbot that uses FMP data to answer financial questions."""

import os
from typing import Optional
from anthropic import Anthropic
from fmp_api import FMPClient
from debt_analyzer import DebtAnalyzer


class FinancialChatbot:
    """Chatbot that answers financial questions using Claude and FMP data."""

    def __init__(self, fmp_api_key: str, claude_api_key: str):
        """
        Initialize the chatbot.

        Args:
            fmp_api_key: Financial Modeling Prep API key
            claude_api_key: Claude API key
        """
        self.fmp_client = FMPClient(fmp_api_key)
        self.claude_client = Anthropic(api_key=claude_api_key)
        self.conversation_history = []
        self.analyzed_companies = {}

    def _fetch_company_debt_data(self, symbol: str) -> Optional[dict]:
        """
        Fetch and analyze debt data for a company.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Analysis result or None if data unavailable
        """
        if symbol in self.analyzed_companies:
            return self.analyzed_companies[symbol]

        try:
            balance_sheets = self.fmp_client.get_balance_sheet(symbol, period="annual", limit=10)

            if not balance_sheets:
                return None

            result = DebtAnalyzer.analyze_company(symbol, balance_sheets)
            self.analyzed_companies[symbol] = result
            return result
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None

    def _extract_companies_from_question(self, question: str) -> list:
        """
        Extract company symbols from user question.

        Args:
            question: User's question

        Returns:
            List of company symbols (uppercased)
        """
        # Common ticker symbols to look for
        common_symbols = {
            "apple": "AAPL",
            "microsoft": "MSFT",
            "google": "GOOGL",
            "alphabet": "GOOGL",
            "amazon": "AMZN",
            "tesla": "TSLA",
            "meta": "META",
            "facebook": "META",
            "nvidia": "NVDA",
            "jpmorgan": "JPM",
            "jp morgan": "JPM",
            "bank of america": "BAC",
            "bofa": "BAC",
            "walmart": "WMT",
        }

        found_symbols = []
        question_lower = question.lower()

        for company_name, symbol in common_symbols.items():
            if company_name in question_lower:
                found_symbols.append(symbol)

        # Also check for direct ticker symbols (4+ consecutive uppercase letters)
        import re
        tickers = re.findall(r'\b([A-Z]{1,5})\b', question)
        for ticker in tickers:
            if ticker not in found_symbols and len(ticker) <= 5:
                found_symbols.append(ticker)

        return list(set(found_symbols))

    def _build_context(self, question: str) -> str:
        """
        Build context about companies mentioned in the question.

        Args:
            question: User's question

        Returns:
            Formatted context string with financial data
        """
        symbols = self._extract_companies_from_question(question)

        if not symbols:
            return ""

        context_parts = ["Financial Data Context:\n"]

        for symbol in symbols:
            result = self._fetch_company_debt_data(symbol)

            if not result or result['status'] == 'no_data':
                context_parts.append(f"\n{symbol}: No data available")
                continue

            debt_data = result.get('debt_data', [])
            earliest_date, earliest_debt = debt_data[0] if debt_data else (None, 0)
            latest_date, latest_debt = debt_data[-1] if debt_data else (None, 0)

            context_parts.append(f"\n{symbol}:")
            context_parts.append(f"  Status: {'Increasing debt' if result['is_increasing'] else 'Decreasing debt'}")
            context_parts.append(f"  Period: {earliest_date} to {latest_date} ({result['data_points']} years)")
            context_parts.append(f"  Debt Change: {result['debt_change_pct']:+.1f}%")
            context_parts.append(f"  Earliest Debt: ${result['earliest_debt']:,.0f}")
            context_parts.append(f"  Latest Debt: ${result['latest_debt']:,.0f}")
            context_parts.append(f"  Average Debt: ${result['average_debt']:,.0f}")
            context_parts.append(f"  Trend Slope: {result['trend_slope']:+.0f}")

        return "\n".join(context_parts)

    def chat(self, user_message: str) -> str:
        """
        Send a message and get a response from Claude.

        Args:
            user_message: User's question or statement

        Returns:
            Claude's response
        """
        # Build context with relevant financial data
        context = self._build_context(user_message)

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Prepare system message with financial expertise
        system_message = """You are a financial analyst chatbot with access to real company balance sheet data
from the Financial Modeling Prep API.

You have the following information available:
1. Real balance sheet data for companies
2. Debt trend analysis using linear regression
3. Historical financial metrics

When answering questions:
- Use the provided financial data to make informed observations
- Explain what the data shows about debt trends
- Provide context about what the numbers mean
- Be concise but thorough
- If asked about companies not in your data, acknowledge the limitation

If financial data is provided, incorporate it directly into your response."""

        if context:
            system_message += f"\n\n{context}"

        # Get response from Claude
        response = self.claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_message,
            messages=self.conversation_history
        )

        assistant_message = response.content[0].text

        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message

    def reset_conversation(self):
        """Reset conversation history."""
        self.conversation_history = []
        print("Conversation reset.")

    def show_analyzed_companies(self):
        """Show which companies have been analyzed."""
        if not self.analyzed_companies:
            print("No companies analyzed yet.")
            return

        print("\nAnalyzed Companies:")
        for symbol, result in self.analyzed_companies.items():
            status = "📈 Increasing" if result['is_increasing'] else "📉 Decreasing"
            change = result['debt_change_pct']
            print(f"  {symbol}: {status} ({change:+.1f}%)")
