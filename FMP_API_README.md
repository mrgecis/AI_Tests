# Financial Modeling Prep API Integration

This project provides tools to analyze company balance sheet data using the Financial Modeling Prep API, with a focus on identifying companies with increasing debt over time.

## Features

- **Balance Sheet Analysis**: Fetch and analyze historical balance sheet data
- **Debt Trend Detection**: Identify companies with increasing or decreasing debt
- **Multiple Companies**: Analyze multiple companies in batch
- **Detailed Reports**: Get comprehensive debt metrics and trends

## Setup

### 1. Get an API Key

1. Visit [Financial Modeling Prep](https://site.financialmodelingprep.com/login)
2. Create a free account
3. Copy your API key from the dashboard

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Then edit `.env` and add your API key:

```
FMP_API_KEY=your_api_key_here
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Run Debt Analysis

```bash
python3 analyze_debt.py
```

This will analyze the predefined list of companies (AAPL, MSFT, GOOGL, etc.) and report which ones have increasing or decreasing debt.

### Customize Company List

Edit `analyze_debt.py` and modify the `symbols` list in the `main()` function:

```python
symbols = [
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    # Add more symbols here
]
```

### Run Tests

```bash
python3 test_fmp_integration.py
```

This runs the integration tests with mock data to verify the system is working correctly.

## Project Structure

```
.
├── requirements.txt          # Python dependencies
├── .env.example             # Example environment configuration
├── fmp_api.py              # FMP API client
├── debt_analyzer.py         # Debt analysis logic
├── analyze_debt.py          # Main analysis script
└── test_fmp_integration.py # Integration tests
```

## Modules

### `fmp_api.py`

The `FMPClient` class handles all API communication:

- `get_balance_sheet(symbol, period='annual', limit=10)` - Fetch balance sheet data
- `get_company_profile(symbol)` - Get company information
- `get_available_symbols(limit=100)` - Get list of available stocks

### `debt_analyzer.py`

The `DebtAnalyzer` class performs debt analysis:

- `extract_debt_data(balance_sheets)` - Extract debt from balance sheets
- `is_debt_increasing(debt_data)` - Determine trend using linear regression
- `analyze_company(symbol, balance_sheets)` - Full analysis for a company

## How It Works

1. **Data Fetching**: Retrieves 10 years of annual balance sheet data for each company
2. **Debt Extraction**: Calculates total debt (short-term + long-term debt)
3. **Trend Analysis**: Uses linear regression to determine if debt is increasing or decreasing
4. **Reporting**: Displays results with metrics like:
   - Debt change percentage
   - Trend slope
   - Time period covered
   - Earliest and latest debt amounts

## API Endpoints Used

- `/balance-sheet-statement/{symbol}` - Balance sheet data
- `/profile/{symbol}` - Company profile information
- `/available-traded/list` - Available stock symbols

## Output Example

```
📈 COMPANIES WITH INCREASING DEBT (3)
────────────────────────────────────────────────────────────────────────────────

TSLA
  Period: 2015-12-31 to 2024-12-31 (10 years)
  Debt increased by +15.3%
  2015-12-31: $1.50B
  2024-12-31: $1.73B
  Trend slope: +2500
```

## Limitations

- Free tier API may have rate limits
- Historical data availability varies by company
- Analysis is based on total debt; doesn't account for asset growth or profitability

## Next Steps

- Add more analysis metrics (debt-to-equity ratio, interest coverage)
- Export results to CSV or Excel
- Create visualizations of debt trends
- Add filtering by industry or market cap
- Schedule periodic analysis reports

## Support

For API documentation, visit: https://site.financialmodelingprep.com/developer/docs
