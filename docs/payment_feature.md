# Payment Summary feature

This document will outline how I'm planning to implement the payment feature.

## Context

This tool is meant for my personal use, keeping track of my expenses among two distinct budgets, one for my regular expenses, and another one meant for investments, such as my family funds, my retirement plan, etc. Those are irregular, meaning sometimes I invest funds, sometimes I just save the funds and keep them stored in a CETES account or similar until the time is right.

The challenge I have is, the current budgeting system I have (powered by YNAB) is somewhat complex to navigate, making it hard for me to know what savings and debit accounts I can use to pay my credit cards and other deposits on a monthly basis. The complexity is added when some credit cards are shared between the two budgets, where some expenses should be covered by A source and some others (likely from the other budget) should be covered from B source.

I am thinking of solving this problem by introducing the idea of a 1 to N relationship between the credit cards and my debit sources through this repository.

Ultimately, the payment summary should be an easy to follow recipe of what account should be moving what money where, and it should be loaded on a new page of the spreadsheet (Ledger) we use as source of truth, such that I can monthly use that to easily sit down in a quick 20 minute session and perform all my transactions such that payments are done.

## Detailed Design

### Summary

The payment feature will solve the multi-budget credit card payment problem through these key steps:

1. **Leverage Existing Ledger Data**: Use the daily-updated "Cuentas" worksheet as the primary data source instead of fresh YNAB API calls
2. **Payment Rule Engine**: Create configurable rules that map credit cards to their eligible payment sources with priority ordering
3. **Smart Payment Calculator**: Algorithm that optimizes payments based on cached balance data, debt amounts, and user-defined rules
4. **Payment Summary Generation**: Create actionable "recipes" in Google Sheets showing exactly which account pays what amount to which credit card
5. **Workflow Integration**: Seamlessly integrate with existing daily update workflow and notification systems

### Technical Design

#### Architecture Overview

The solution extends your existing clean architecture by leveraging the daily-updated ledger:

- **Data Layer**: Primary data source from existing "Cuentas" worksheet (updated daily via `daily-ynab-update.yml`)
- **Business Logic**: New payment engine (`src/payment/`)
- **Presentation Layer**: Extended Google Sheets integration (`src/gsheets/`) for Payment Summary output
- **Orchestration**: New payment workflow (`src/workflows/`) that reads from cached ledger data

#### Core Components

**1. Enhanced Data Models** (`src/ynab/ynab_types.py`)

```python
class YNABAccount(TypedDict):
    name: str
    balance: float
    account_type: str  # "credit_card", "checking", "savings"
    budget_id: str
    consolidated: bool
    payment_due_date: Optional[int]  # Day of month (1-31) from "Fecha Pago" column

class PaymentRule(TypedDict):
    credit_card_name: str
    budget_id: str  # "main" or "secondary"
    debit_sources: list[str]  # Priority-ordered payment sources

class PaymentConfig(TypedDict):
    default_payment_sources: dict[str, list[str]]  # budget_id -> default sources
    payment_rules: list[PaymentRule]

class PaymentTransfer(TypedDict):
    """Represents a single transfer from one source account to pay a credit card"""
    credit_card: str
    budget_id: str
    total_card_debt: float
    transfer_source: str  # Source account name
    transfer_amount: float
    remaining_card_balance: float
    payment_due_date: Optional[int]  # Day of month
    days_until_due: int  # For urgency calculation
    rule_type: str  # "explicit" or "default"
    strategy_used: str
    notes: str  # e.g., "Transfer 1 of 2"
```

**2. Payment Rule Engine** (`src/payment/rule_engine.py`)

- Configurable JSON rules mapping credit cards to payment sources
- Priority-ordered debit account lists per credit card
- **Default payment sources per budget** for credit cards without specific rules
- Budget-specific rule validation against actual account names
- Handles same credit card across different budgets with budget-specific rules

**3. Payment Strategy System** (`src/payment/strategies/`)

- **Strategy Pattern Architecture**: Extensible payment calculation using pluggable strategies
- **Default Strategy**: Priority-ordered payment (simple, predictable)
- **Strategy Factory**: Manages strategy creation and registration for extensibility
- **Per-card Strategy Selection**: Each credit card can use different payment strategies
- **Strategy Configuration**: Fine-tune strategy behavior via JSON configuration

**4. Payment Calculator** (`src/payment/calculator.py`)

- **Strategy-Aware Engine**: Uses strategy factory to select appropriate payment algorithm
- **Targets full balance payment** - attempts to pay entire credit card balance
- **Handles edge cases** via strategy-specific logic (low balances, insufficient funds, etc.)
- No due date logic - processes all credit cards with negative balances

**5. Google Sheets Payment Integration** (`src/gsheets/payment_ledger.py`)

- **Smart Sheet Management**: Finds existing "Payment Summary" worksheet or creates new one
- **Content Replacement**: Overwrites existing payment data with fresh calculations
- **Structured Payment Table**: Well-defined columns and formatting for easy manual processing
- **Status Tracking**: Allows marking payments as completed for progress tracking

**5. Payment Workflow** (`src/workflows/payment_generator.py`)

- Orchestrates entire payment summary generation process
- **Targets full balance payment** for all credit cards with negative balances
- No due date awareness - assumes user wants to pay all cards when triggered
- Integrates with existing email notification system
- Supports dry-run mode for testing

**6. GitHub Actions Integration**

- **Twice-monthly automatic runs**: 1st and 16th of each month at 6:00 AM Mexico City time
- **Manual trigger capability**: Run on-demand anytime via workflow_dispatch
- Integrates with existing workflow patterns similar to `daily-ynab-update.yml`

#### Data Flow Sequence

1. **Load Configuration**: Read payment rules and default sources from JSON config file
2. **Read Ledger Data**: Load account balances AND payment due dates from existing "Cuentas" worksheet (column H "Fecha Pago")
3. **Identify Credit Card Debts**: Filter for accounts with negative balances to find cards requiring payment
4. **Calculate Payment Urgency**: For each credit card, calculate days until due date using current date vs "Fecha Pago"
5. **Calculate Available Funds**: Sum positive balances from checking/savings accounts per budget
6. **Apply Payment Rules and Strategy Selection**: For each credit card with debt:
   - Look for explicit rule matching credit card name + budget ID
   - If no explicit rule found, use default payment sources for that budget
   - Determine payment strategy (defaults to "priority_ordered" if not specified)
   - Validate that payment sources exist in the ledger data
7. **Execute Payment Strategy**: Generate **PaymentTransfer** objects (one per source account transfer)
8. **Sort by Urgency**: Order transfers by days until due date (most urgent first)
9. **Write to Google Sheets**: Create transaction-oriented "Payment Summary" worksheet with transfers as individual rows
10. **Send Notifications**: Email summary using existing notification system

#### Integration with Existing System

- **Primary Dependency**: `daily-ynab-update.yml` workflow keeps "Cuentas" worksheet current (runs daily at 8 AM)
- **Data Source**: Reads from existing `src/gsheets/ledger.py` utilities instead of fresh YNAB API calls
- **Follows** `src/workflows/balance_checker.py` workflow patterns for structure
- **Leverages** existing email infrastructure from `src/resend/`
- **Maintains** environment-based configuration approach
- **Minimal YNAB API Dependency**: Payment feature relies on cached data, not direct API calls
- **GitHub Actions**: New workflow similar to `daily-ynab-update.yml` structure

#### Key Advantages of Leveraging Existing Ledger

- **Performance**: Much faster execution (reading from Google Sheets vs multiple YNAB API calls)
- **Consistency**: Payment decisions based on same data visible in your UI
- **Reliability**: Less dependent on YNAB API availability during payment generation
- **Data Freshness**: Ledger updated daily ensures recent balance information

#### GitHub Workflow Implementation

```yaml
name: Payment Summary Generator
on:
  schedule:
    - cron: "0 12 1 * *" # 1st of every month at 6:00 AM Mexico City (UTC-6)
    - cron: "0 12 16 * *" # 16th of every month at 6:00 AM Mexico City (UTC-6)
  workflow_dispatch: # Manual trigger anytime

jobs:
  generate-payment-summary:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Create service account JSON file
        run: |
          echo '${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}' > service-account.json
        env:
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}

      - name: Generate Payment Summary
        run: |
          python3 payment_summary.py
        env:
          GSHEETS_SERVICE_ACCOUNT_FILE: ./service-account.json
          GSHEETS_SPREADSHEET_ID: ${{ secrets.GSHEETS_SPREADSHEET_ID }}

      - name: Clean up service account file
        run: rm -f service-account.json
        if: always()
```

#### Configuration Example

```json
{
  "default_payment_sources": {
    "main_budget": ["Main Checking", "Main Savings"],
    "secondary_budget": ["Investment Checking", "CETES Account"]
  },
  "payment_rules": [
    {
      "credit_card_name": "Chase Sapphire",
      "budget_id": "main",
      "debit_sources": ["Main Checking", "Emergency Savings"]
    },
    {
      "credit_card_name": "Chase Sapphire",
      "budget_id": "secondary",
      "debit_sources": ["Investment Checking", "CETES Account"]
    },
    {
      "credit_card_name": "Investment Credit Card",
      "budget_id": "secondary",
      "debit_sources": ["Investment Checking", "Main Checking"]
    }
  ]
}
```

**Key Configuration Features:**

- **Default Payment Sources**: Per-budget fallback when no specific rule exists for a credit card
- **Same Credit Card, Different Budgets**: "Chase Sapphire" appears in both budgets with different payment sources
- **Budget-Specific Rules**: Each rule specifies `budget_id` to handle account availability per budget
- **Flexible Fallback**: Any credit card without explicit rules uses the appropriate default sources

This design follows **SRP** (single responsibility per module), **DRY** (reuses existing patterns), and **KISS** (simple data flow) while maximizing integration with your current YNAB API and Google Sheets infrastructure.

#### Payment Summary Worksheet Structure

The Payment Summary worksheet will be structured as a **transaction-oriented list** for optimal manual processing during your monthly payment sessions.

**Worksheet Name**: `"Payment Summary"` (or `"Resumen de Pagos"` for Spanish)

**Transaction-Based Column Structure**:

| Column | Field                  | Description                                | Format   | Example           |
| ------ | ---------------------- | ------------------------------------------ | -------- | ----------------- |
| A      | **Prioridad**          | Urgency rank (days until due)              | Number   | "2"               |
| B      | **Fecha Pago**         | Credit card payment due date               | Date     | "2024-01-28"      |
| C      | **Tarjeta de Crédito** | Credit card name from YNAB                 | Text     | "Amex Gold"       |
| D      | **Saldo Total**        | Total credit card debt                     | Currency | "-$25,000.00"     |
| E      | **Transferir de**      | Source account for this transfer           | Text     | "Cuenta Maestra"  |
| F      | **Monto Transferir**   | Amount to transfer from this source        | Currency | "$15,000.00"      |
| G      | **Saldo Restante**     | Remaining card balance after this transfer | Currency | "$10,000.00"      |
| H      | **Presupuesto**        | Budget source (main/secondary)             | Text     | "Main"            |
| I      | **Estado**             | Transfer status for tracking               | Dropdown | "Pendiente"       |
| J      | **Fecha Procesado**    | Date when transfer was made                | Date     | "2024-01-26"      |
| K      | **Notas**              | Additional notes or comments               | Text     | "Transfer 1 of 2" |

**Key Design Changes**:

- **One row = One transfer**: Each row represents a single transfer from one source account
- **Multiple rows per card**: Cards requiring multiple source accounts get multiple rows
- **Urgency-based ordering**: Sorted by days until payment due date (most urgent first)
- **Transfer-focused language**: "Transferir de" instead of generic "payment source"

**Sheet Formatting**:

- **Header Row**: Bold, background color, frozen for scrolling
- **Currency Columns**: Mexican peso formatting (`$#,##0.00`)
- **Status Column**: Data validation dropdown with options:
  - "Pendiente" (Pending)
  - "Procesado" (Processed)
  - "Verificado" (Verified)
  - "Error" (Error)
- **Conditional Formatting**:
  - Red background for negative balances
  - Green background for completed payments
  - Yellow background for partial payments

**Summary Section** (Below payment data):

- **Total Debt**: Sum of all credit card balances
- **Total Payments**: Sum of all payment amounts
- **Accounts Used**: List of unique payment source accounts
- **Generation Date**: Timestamp when summary was created
- **Strategy Breakdown**: Count of each payment strategy used

#### Smart Sheet Management Implementation

**Sheet Discovery and Creation Logic** (`src/gsheets/payment_ledger.py`):

```python
def get_or_create_payment_worksheet() -> gspread.Worksheet:
    """Smart worksheet management - find existing or create new Payment Summary sheet"""

    # List of possible sheet names to search for (multi-language support)
    PAYMENT_SHEET_NAMES = [
        "Payment Summary",
        "Resumen de Pagos",
        "Payments",
        "Pagos"
    ]

    client = get_gsheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    # Try to find existing payment worksheet
    existing_worksheet = None
    for sheet_name in PAYMENT_SHEET_NAMES:
        try:
            existing_worksheet = spreadsheet.worksheet(sheet_name)
            print(f"Found existing payment worksheet: '{sheet_name}'")
            break
        except gspread.exceptions.WorksheetNotFound:
            continue

    # If found, return existing worksheet for content replacement
    if existing_worksheet:
        return existing_worksheet

    # If not found, create new worksheet
    try:
        new_worksheet = spreadsheet.add_worksheet(
            title="Payment Summary",
            rows=100,  # Initial size
            cols=11    # Number of columns defined above
        )
        print("Created new 'Payment Summary' worksheet")

        # Set up initial formatting and headers
        setup_payment_worksheet_formatting(new_worksheet)

        return new_worksheet

    except Exception as e:
        raise RuntimeError(f"Failed to create Payment Summary worksheet: {e}")

def setup_payment_worksheet_formatting(worksheet: gspread.Worksheet) -> None:
    """Initialize worksheet with headers, formatting, and validation"""

    # Define headers
    headers = [
        "Tarjeta de Crédito",
        "Presupuesto",
        "Saldo Actual",
        "Monto a Pagar",
        "Cuenta de Origen",
        "Estrategia",
        "Tipo de Regla",
        "Balance Restante",
        "Estado",
        "Fecha Procesado",
        "Notas"
    ]

    # Set headers in row 1
    worksheet.update('A1:K1', [headers])

    # Apply header formatting
    worksheet.format('A1:K1', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
        'horizontalAlignment': 'CENTER'
    })

    # Set column widths
    worksheet.columns_auto_resize(0, 10)  # Auto-resize all columns

    # Add data validation for Status column (I)
    validation_rule = {
        'condition': {
            'type': 'ONE_OF_LIST',
            'values': ['Pendiente', 'Procesado', 'Verificado', 'Error']
        },
        'showCustomUi': True
    }
    worksheet.add_validation('I2:I100', validation_rule)

    # Freeze header row
    worksheet.freeze(1)

def write_payment_instructions(
    worksheet: gspread.Worksheet,
    instructions: list[PaymentInstruction],
    generation_timestamp: str
) -> None:
    """Replace worksheet content with fresh payment instructions"""

    # Clear existing payment data (keep headers)
    worksheet.clear('A2:K100')

    if not instructions:
        # Add "No payments needed" message
        worksheet.update('A2', [["No hay pagos requeridos en este momento"]])
        return

    # Prepare data rows
    data_rows = []
    for instruction in instructions:
        row = [
            instruction["credit_card"],
            instruction["budget_id"].title(),
            f"-${abs(instruction['amount_due']):,.2f}",
            f"${instruction['payment_amount']:,.2f}",
            instruction["payment_source"],
            instruction.get("strategy_used", "priority_ordered"),
            instruction["rule_type"],
            f"${instruction['remaining_balance']:,.2f}",
            "Pendiente",  # Default status
            "",  # Date processed (empty initially)
            ""   # Notes (empty initially)
        ]
        data_rows.append(row)

    # Write all data at once for efficiency
    if data_rows:
        range_end = f"K{len(data_rows) + 1}"
        worksheet.update(f'A2:{range_end}', data_rows)

    # Add summary section
    summary_start_row = len(data_rows) + 4
    add_summary_section(worksheet, instructions, generation_timestamp, summary_start_row)

    # Apply conditional formatting
    apply_payment_conditional_formatting(worksheet, len(data_rows))

def add_summary_section(
    worksheet: gspread.Worksheet,
    instructions: list[PaymentInstruction],
    timestamp: str,
    start_row: int
) -> None:
    """Add summary statistics below the payment data"""

    total_debt = sum(abs(inst['amount_due']) for inst in instructions)
    total_payments = sum(inst['payment_amount'] for inst in instructions)
    unique_accounts = set(inst['payment_source'] for inst in instructions)
    strategy_counts = {}

    for inst in instructions:
        strategy = inst.get('strategy_used', 'priority_ordered')
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

    summary_data = [
        ["RESUMEN DE PAGOS", ""],
        ["", ""],
        ["Total Deuda:", f"${total_debt:,.2f}"],
        ["Total Pagos:", f"${total_payments:,.2f}"],
        ["Cuentas Utilizadas:", f"{len(unique_accounts)}"],
        ["", ""],
        ["Generado el:", timestamp],
        ["", ""],
        ["ESTRATEGIAS UTILIZADAS:", ""]
    ]

    for strategy, count in strategy_counts.items():
        summary_data.append([f"  {strategy}:", f"{count} tarjetas"])

    # Write summary
    end_row = start_row + len(summary_data) - 1
    worksheet.update(f'A{start_row}:B{end_row}', summary_data)

    # Format summary header
    worksheet.format(f'A{start_row}', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
    })
```

**Key Smart Management Features**:

- **Multi-language Detection**: Searches for sheet names in both English and Spanish
- **Graceful Creation**: Creates new worksheet if none exists
- **Content Replacement**: Clears and rewrites payment data while preserving structure
- **Formatting Preservation**: Maintains headers, validation, and conditional formatting
- **Error Handling**: Provides clear error messages if worksheet operations fail
- **Summary Statistics**: Automatically calculates totals and strategy breakdowns

This approach ensures the Payment Summary worksheet is always ready for your monthly payment sessions with fresh, properly formatted data.

## Alternatives

Here are three different approaches considered for solving this payment optimization problem:

### Alternative 1: Manual Configuration in Google Sheets (Recommended Above)

**Approach**: External JSON configuration file + automated Google Sheets generation

- **Pros**:
  - Flexible rule configuration without code changes
  - Clean separation of business logic and configuration
  - Leverages existing Google Sheets infrastructure
  - Easy to modify payment rules
- **Cons**:
  - Requires maintaining separate config file
  - Initial setup complexity for non-technical users
- **Verdict**: ✅ **Selected** - Best balance of flexibility, maintainability, and integration

### Alternative 2: Embedded Rules in Google Sheets

**Approach**: Store payment rules directly in a "Payment Rules" worksheet tab

- **Implementation**:
  - Create "Payment Rules" sheet with columns: Credit Card, Payment Source 1, Payment Source 2, etc.
  - Read rules from Google Sheets instead of JSON file
  - Use existing `src/gsheets/ledger.py` patterns to load rule data
- **Pros**:
  - All configuration in one place (Google Sheets)
  - No separate config files to manage
  - Easy for non-technical users to modify rules
  - Leverages existing Google Sheets expertise
- **Cons**:
  - Less version control for rule changes
  - Harder to validate rule format
  - More complex sheet structure
- **Verdict**: 🤔 **Alternative** - Good for users who prefer sheet-based configuration

### Alternative 3: YNAB Category-Based Payment Logic

**Approach**: Use YNAB category assignments to determine payment sources automatically

- **Implementation**:
  - Analyze recent transactions per credit card
  - Determine which budget (main/secondary) has more activity
  - Automatically assign payment source based on transaction patterns
  - Use machine learning/heuristics to improve assignments over time
- **Pros**:
  - Fully automated - no manual rule configuration needed
  - Adapts to changing spending patterns automatically
  - Leverages rich YNAB transaction data
- **Cons**:
  - Much more complex implementation
  - Less predictable/controllable behavior
  - Requires transaction analysis capabilities
  - May not handle edge cases well (shared cards, irregular spending)
  - Harder to debug when payments seem "wrong"
- **Verdict**: ❌ **Rejected** - Violates KISS principle, adds unnecessary complexity

### Alternative 4: Hybrid Approach with Smart Defaults

**Approach**: Combine explicit rules with intelligent defaults based on YNAB data

- **Implementation**:
  - Start with Alternative 1's rule engine
  - Add fallback logic that analyzes transaction patterns when no explicit rule exists
  - Provide suggestions for new payment rules based on spending analysis
- **Pros**:
  - Best of both worlds - explicit control with intelligent assistance
  - Handles new credit cards automatically
  - Learns from actual usage patterns
- **Cons**:
  - More complex to implement and maintain
  - Two different logic paths to debug
  - May confuse users about which logic is being applied
- **Verdict**: 🔄 **Future Enhancement** - Consider for v2.0 after core functionality is proven

### Decision Rationale

**Alternative 1** was selected as the recommended approach because it:

1. **Maximizes Integration**: Builds naturally on your existing YNAB + Google Sheets architecture
2. **Follows KISS**: Simple, predictable logic flow that's easy to understand and debug
3. **Maintains Control**: User has full control over payment logic without surprises
4. **Enables Iteration**: Easy to modify rules and test different payment strategies
5. **Leverages Strengths**: Uses your existing patterns and infrastructure effectively

The modular design also allows easy migration to Alternative 2 (sheet-based rules) later if desired, without changing the core payment engine logic.

---

## Payment Strategy Engine Design

This section explores how to design an extensible payment strategy system that follows the **Open-Closed Principle (OCP)** - allowing new payment strategies to be added without modifying existing code.

### Problem Statement

The current design assumes a simple priority-ordered payment approach, but real-world payment scenarios require more sophisticated strategies:

- **Low Balance Handling**: What if a debit account has insufficient funds?
- **Distribution Strategies**: Should payments be split across multiple sources?
- **Category-Based Logic**: Pay from accounts based on spending category analysis?
- **Percentage-Based Allocation**: Split payments by predefined percentages?
- **Smart Optimization**: Minimize fees, maximize cashback, or maintain minimum balances?

### Strategy Pattern Architecture

#### Core Interface Design (`src/payment/strategies/base_strategy.py`)

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.ynab.ynab_types import PaymentInstruction, YNABAccount, PaymentRule

class PaymentStrategy(ABC):
    """Abstract base class for payment strategies"""

    @abstractmethod
    def calculate_payments(
        self,
        credit_card: YNABAccount,
        available_sources: List[YNABAccount],
        rule: PaymentRule,
        strategy_config: Dict[str, Any]
    ) -> List[PaymentInstruction]:
        """Calculate how to pay a credit card using available sources"""
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        pass

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate strategy-specific configuration"""
        return True
```

#### Strategy Implementations

**1. Priority-Ordered Strategy** (`src/payment/strategies/priority_strategy.py`)

```python
class PriorityOrderedStrategy(PaymentStrategy):
    """Pay using debit sources in priority order until full balance is covered"""

    def calculate_payments(self, credit_card, available_sources, rule, strategy_config):
        target_amount = abs(credit_card["balance"])
        remaining_debt = target_amount
        instructions = []

        # Sort sources by rule priority
        ordered_sources = self._sort_by_priority(available_sources, rule["debit_sources"])

        for source in ordered_sources:
            if remaining_debt <= 0:
                break

            available_amount = max(0, source["balance"] - strategy_config.get("min_balance", 0))
            payment_amount = min(remaining_debt, available_amount)

            if payment_amount > 0:
                instructions.append({
                    "credit_card": credit_card["name"],
                    "budget_id": credit_card["budget_id"],
                    "amount_due": target_amount,
                    "payment_source": source["name"],
                    "payment_amount": payment_amount,
                    "remaining_balance": remaining_debt - payment_amount,
                    "rule_type": "explicit",
                    "strategy_used": "priority_ordered"
                })
                remaining_debt -= payment_amount

        return instructions
```

**2. Even Distribution Strategy** (`src/payment/strategies/distribution_strategy.py`)

```python
class EvenDistributionStrategy(PaymentStrategy):
    """Distribute payment evenly across available sources"""

    def calculate_payments(self, credit_card, available_sources, rule, strategy_config):
        target_amount = abs(credit_card["balance"])

        # Calculate available capacity from each source
        available_sources = self._filter_available_sources(available_sources, strategy_config)

        if not available_sources:
            return []

        # Distribute evenly with minimum payment amounts
        min_payment = strategy_config.get("min_payment_per_source", 50)
        total_capacity = sum(source["capacity"] for source in available_sources)

        if total_capacity < target_amount:
            # Not enough capacity - fall back to priority strategy
            return PriorityOrderedStrategy().calculate_payments(credit_card, available_sources, rule, strategy_config)

        instructions = []
        for source in available_sources:
            payment_ratio = source["capacity"] / total_capacity
            payment_amount = max(min_payment, target_amount * payment_ratio)

            instructions.append({
                "credit_card": credit_card["name"],
                "budget_id": credit_card["budget_id"],
                "amount_due": target_amount,
                "payment_source": source["name"],
                "payment_amount": payment_amount,
                "remaining_balance": 0,  # Distributed payment
                "rule_type": "explicit",
                "strategy_used": "even_distribution"
            })

        return instructions
```

**3. Category-Based Strategy** (`src/payment/strategies/category_strategy.py`)

```python
class CategoryBasedStrategy(PaymentStrategy):
    """Pay from accounts based on spending category analysis"""

    def calculate_payments(self, credit_card, available_sources, rule, strategy_config):
        # This would analyze recent transactions for the credit card
        # and determine payment sources based on spending categories

        # Example: If 60% of spending was on "Groceries" and "Groceries"
        # is funded by "Main Checking", pay 60% from Main Checking

        category_breakdown = self._analyze_spending_categories(credit_card, strategy_config)
        source_allocation = self._map_categories_to_sources(category_breakdown, rule, strategy_config)

        return self._create_category_based_instructions(credit_card, source_allocation)
```

### Enhanced Configuration System

#### Strategy Configuration (`payment_rules.json`)

```json
{
  "default_payment_sources": {
    "main_budget": ["Main Checking", "Main Savings"],
    "secondary_budget": ["Investment Checking", "CETES Account"]
  },
  "payment_rules": [
    {
      "credit_card_name": "Chase Sapphire",
      "budget_id": "main",
      "debit_sources": ["Main Checking", "Emergency Savings"],
      "strategy": "priority_ordered",
      "strategy_config": {
        "min_balance": 500,
        "max_payment_per_source": 5000
      }
    },
    {
      "credit_card_name": "Investment Credit Card",
      "budget_id": "secondary",
      "debit_sources": [
        "Investment Checking",
        "CETES Account",
        "Main Checking"
      ],
      "strategy": "even_distribution",
      "strategy_config": {
        "min_payment_per_source": 100,
        "min_balance": 1000
      }
    },
    {
      "credit_card_name": "Shared Family Card",
      "budget_id": "main",
      "debit_sources": ["Main Checking", "Family Savings"],
      "strategy": "category_based",
      "strategy_config": {
        "analysis_period_months": 1,
        "category_mappings": {
          "Groceries": "Main Checking",
          "Family Activities": "Family Savings"
        },
        "fallback_strategy": "priority_ordered"
      }
    }
  ],
  "global_strategy_defaults": {
    "priority_ordered": {
      "min_balance": 200
    },
    "even_distribution": {
      "min_payment_per_source": 50,
      "min_balance": 300
    }
  }
}
```

### Strategy Factory and Manager

#### Strategy Factory (`src/payment/strategy_factory.py`)

```python
from typing import Dict, Type
from src.payment.strategies.base_strategy import PaymentStrategy
from src.payment.strategies.priority_strategy import PriorityOrderedStrategy
from src.payment.strategies.distribution_strategy import EvenDistributionStrategy
from src.payment.strategies.category_strategy import CategoryBasedStrategy

class PaymentStrategyFactory:
    """Factory for creating payment strategy instances"""

    _strategies: Dict[str, Type[PaymentStrategy]] = {
        "priority_ordered": PriorityOrderedStrategy,
        "even_distribution": EvenDistributionStrategy,
        "category_based": CategoryBasedStrategy,
    }

    @classmethod
    def create_strategy(cls, strategy_name: str) -> PaymentStrategy:
        """Create a strategy instance by name"""
        if strategy_name not in cls._strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        return cls._strategies[strategy_name]()

    @classmethod
    def register_strategy(cls, name: str, strategy_class: Type[PaymentStrategy]):
        """Register a new strategy (for extensibility)"""
        cls._strategies[name] = strategy_class

    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Get list of available strategy names"""
        return list(cls._strategies.keys())
```

#### Updated Payment Calculator (`src/payment/calculator.py`)

```python
from src.payment.strategy_factory import PaymentStrategyFactory

class PaymentCalculator:
    def __init__(self, rule_engine):
        self.rule_engine = rule_engine
        self.strategy_factory = PaymentStrategyFactory()

    def calculate_payments(self, credit_cards, available_funds, global_config):
        all_instructions = []

        for card in credit_cards:
            if card["balance"] >= 0:  # Skip cards without debt
                continue

            # Get payment rule and strategy
            rule = self.rule_engine.get_payment_rule(card)
            strategy_name = rule.get("strategy", "priority_ordered")
            strategy_config = self._merge_configs(rule.get("strategy_config", {}), global_config)

            # Create strategy instance and calculate payments
            strategy = self.strategy_factory.create_strategy(strategy_name)
            available_sources = self._get_available_sources(card, available_funds, rule)

            instructions = strategy.calculate_payments(card, available_sources, rule, strategy_config)
            all_instructions.extend(instructions)

        return all_instructions
```

### Extension Points and Benefits

#### Adding New Strategies (OCP Compliance)

1. **Create new strategy class** inheriting from `PaymentStrategy`
2. **Register strategy** in factory: `PaymentStrategyFactory.register_strategy("my_strategy", MyStrategy)`
3. **Update configuration** to use new strategy name
4. **No changes** to existing payment calculator or workflow code

#### Possible Future Strategies

- **`fee_minimizing`**: Choose sources to minimize transaction fees
- **`cashback_optimizing`**: Maximize cashback by leaving specific amounts in certain accounts
- **`seasonal_based`**: Adjust payment sources based on time of year
- **`balance_maintaining`**: Keep minimum balances across all accounts
- **`debt_avalanche`**: Prioritize highest-interest debt payments
- **`envelope_respecting`**: Follow envelope budgeting principles

#### Benefits of This Architecture

- ✅ **Extensible**: Add new strategies without changing core code
- ✅ **Configurable**: Each strategy has custom configuration options
- ✅ **Testable**: Each strategy can be unit tested independently
- ✅ **Maintainable**: Clear separation of concerns between strategies
- ✅ **Flexible**: Mix different strategies for different credit cards
- ✅ **Backwards Compatible**: Default to simple priority strategy for existing rules

This design allows you to start with simple priority-ordered payments and gradually add more sophisticated strategies as your needs evolve, without disrupting the core payment engine architecture.
