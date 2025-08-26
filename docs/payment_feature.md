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

class PaymentRule(TypedDict):
    credit_card_name: str
    budget_id: str  # "main" or "secondary"
    debit_sources: list[str]  # Priority-ordered payment sources

class PaymentConfig(TypedDict):
    default_payment_sources: dict[str, list[str]]  # budget_id -> default sources
    payment_rules: list[PaymentRule]

class PaymentInstruction(TypedDict):
    credit_card: str
    budget_id: str
    amount_due: float
    payment_source: str
    payment_amount: float
    remaining_balance: float
    rule_type: str  # "explicit" or "default"
```

**2. Payment Rule Engine** (`src/payment/rule_engine.py`)
- Configurable JSON rules mapping credit cards to payment sources
- Priority-ordered debit account lists per credit card
- **Default payment sources per budget** for credit cards without specific rules
- Budget-specific rule validation against actual account names
- Handles same credit card across different budgets with budget-specific rules

**3. Payment Calculator** (`src/payment/calculator.py`)  
- Core algorithm: For each credit card debt, find best payment source based on rules and available funds
- **Targets full balance payment** - attempts to pay entire credit card balance
- Handles insufficient funds scenarios by paying maximum possible amount
- No due date logic - processes all credit cards with negative balances

**4. Google Sheets Payment Integration** (`src/gsheets/payment_ledger.py`)
- Creates/manages "Payment Summary" worksheet
- Writes actionable payment instructions with columns:
  - Credit Card, Current Balance, Amount to Pay, Payment Source, Status
- Allows marking payments as completed

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
2. **Read Ledger Data**: Load current account balances from existing "Cuentas" worksheet (updated daily by `daily-ynab-update.yml`)
3. **Identify Credit Card Debts**: Filter for accounts with negative balances to find cards requiring payment
4. **Calculate Available Funds**: Sum positive balances from checking/savings accounts per budget
5. **Apply Payment Rules**: For each credit card with debt:
   - Look for explicit rule matching credit card name + budget ID  
   - If no explicit rule found, use default payment sources for that budget
   - Validate that payment sources exist in the ledger data
6. **Generate Payment Instructions**: Calculate payment amounts to **pay full balances** based on available funds and rule priority
7. **Write to Google Sheets**: Create "Payment Summary" worksheet with actionable payment instructions
8. **Send Notifications**: Email summary using existing notification system

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
    - cron: '0 12 1 * *'   # 1st of every month at 6:00 AM Mexico City (UTC-6)
    - cron: '0 12 16 * *'  # 16th of every month at 6:00 AM Mexico City (UTC-6)
  workflow_dispatch:       # Manual trigger anytime

jobs:
  generate-payment-summary:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          
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

