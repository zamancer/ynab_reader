from decimal import Decimal
from unittest.mock import Mock, patch

from src.gsheets.ledger import (
    get_credit_cards_with_debt,
    get_debit_sources_with_funds,
    load_accounts_for_payment,
    parse_currency_to_decimal,
    parse_payment_due_date,
)
from src.ynab.ynab_types import YNABAccount


class TestParseCurrencyToDecimal:
    """Test currency parsing to Decimal."""

    def test_parse_valid_currency_string(self):
        """Test parsing valid currency strings."""
        # Arrange & Act & Assert
        assert parse_currency_to_decimal("$1,234.56") == Decimal("1234.56")
        assert parse_currency_to_decimal("-$500.00") == Decimal("-500.00")
        assert parse_currency_to_decimal("1000") == Decimal("1000")
        assert parse_currency_to_decimal("123.45") == Decimal("123.45")

    def test_parse_empty_or_invalid_currency(self):
        """Test parsing empty or invalid currency strings."""
        # Arrange & Act & Assert
        assert parse_currency_to_decimal("") == Decimal("0.0")
        assert parse_currency_to_decimal(None) == Decimal("0.0")
        assert parse_currency_to_decimal("-") == Decimal("0.0")
        assert parse_currency_to_decimal("  ") == Decimal("0.0")

    def test_parse_currency_with_commas_and_spaces(self):
        """Test parsing currency with formatting."""
        # Arrange & Act & Assert
        assert parse_currency_to_decimal("$ 1,234.56 ") == Decimal("1234.56")
        assert parse_currency_to_decimal("$10,000,000.00") == Decimal("10000000.00")

    def test_parse_currency_error_handling(self):
        """Test error handling for invalid currency formats."""
        # Arrange & Act & Assert
        assert parse_currency_to_decimal("invalid") == Decimal("0.0")
        assert parse_currency_to_decimal("$abc.def") == Decimal("0.0")


class TestParsePaymentDueDate:
    """Test payment due date parsing."""

    def test_parse_valid_day_of_month(self):
        """Test parsing valid day of month values."""
        # Arrange & Act & Assert
        assert parse_payment_due_date("15") == 15
        assert parse_payment_due_date("1") == 1
        assert parse_payment_due_date("31") == 31

    def test_parse_date_formats(self):
        """Test parsing various date formats."""
        # Arrange & Act & Assert
        assert parse_payment_due_date("15/01/2024") == 15
        assert parse_payment_due_date("28-02-2024") == 28
        assert parse_payment_due_date("5/12/2024") == 5

    def test_parse_empty_or_invalid_date(self):
        """Test parsing empty or invalid date values."""
        # Arrange & Act & Assert
        assert parse_payment_due_date("") is None
        assert parse_payment_due_date(None) is None
        assert parse_payment_due_date("-") is None
        assert parse_payment_due_date("  ") is None
        assert parse_payment_due_date("invalid") is None

    def test_parse_out_of_range_dates(self):
        """Test parsing out of range day values."""
        # Arrange & Act & Assert
        assert parse_payment_due_date("0") is None
        assert parse_payment_due_date("32") is None
        assert parse_payment_due_date("-5") is None
        assert parse_payment_due_date("100") is None


class TestLoadAccountsForPayment:
    """Test load_accounts_for_payment function."""

    @patch("src.gsheets.ledger.get_worksheet")
    @patch("src.gsheets.ledger.load_sheet_data")
    def test_load_accounts_for_payment_success(
        self, mock_load_sheet_data, mock_get_worksheet
    ):
        """Test successful loading of accounts for payment."""
        # Arrange
        mock_worksheet = Mock()
        mock_get_worksheet.return_value = mock_worksheet

        mock_sheet_data = [
            {
                "Cuenta": "Chase Sapphire",
                "Saldo": "-$1,500.00",
                "Tipo Cuenta": "Credit Card",
                "Fecha Pago": "15",
                "YNAB": "mapped",
            },
            {
                "Cuenta": "Main Checking",
                "Saldo": "$5,000.00",
                "Tipo Cuenta": "Checking",
                "Fecha Pago": "",
                "YNAB": "mapped",
            },
            {
                "Cuenta": "Investment Savings",
                "Saldo": "$10,000.00",
                "Tipo Cuenta": "Savings",
                "Fecha Pago": "",
                "YNAB": "",
            },
        ]
        mock_load_sheet_data.return_value = mock_sheet_data

        # Act
        result = load_accounts_for_payment(testing_flag=True)

        # Assert
        assert len(result) == 3
        # Check credit card account
        credit_card = result[0]
        assert credit_card["name"] == "Chase Sapphire"
        assert credit_card["balance"] == Decimal("-1500.00")
        assert credit_card["account_type"] == "credit_card"
        assert credit_card["budget_id"] == "main"
        assert credit_card["payment_due_date"] == 15
        assert credit_card["consolidated"] is True

        # Check checking account
        checking = result[1]
        assert checking["name"] == "Main Checking"
        assert checking["balance"] == Decimal("5000.00")
        assert checking["account_type"] == "checking"
        assert checking["payment_due_date"] is None

        # Check investment account (secondary budget)
        investment = result[2]
        assert investment["name"] == "Investment Savings"
        assert investment["account_type"] == "savings"
        assert investment["budget_id"] == "secondary"  # Due to "investment" keyword
        assert investment["consolidated"] is False  # No YNAB mapping

        mock_get_worksheet.assert_called_once_with(True)

    @patch("src.gsheets.ledger.get_worksheet")
    @patch("src.gsheets.ledger.load_sheet_data")
    def test_load_accounts_for_payment_skips_empty_rows(
        self, mock_load_sheet_data, mock_get_worksheet
    ):
        """Test that empty rows are skipped."""
        # Arrange
        mock_worksheet = Mock()
        mock_get_worksheet.return_value = mock_worksheet

        mock_sheet_data = [
            {"Cuenta": "", "Saldo": "$1000.00"},  # Empty account name
            {"Cuenta": "Valid Account", "Saldo": "$2000.00", "Tipo Cuenta": "Checking"},
            {"Cuenta": "   ", "Saldo": "$3000.00"},  # Whitespace only
        ]
        mock_load_sheet_data.return_value = mock_sheet_data

        # Act
        result = load_accounts_for_payment()

        # Assert
        assert len(result) == 1
        assert result[0]["name"] == "Valid Account"


class TestGetCreditCardsWithDebt:
    """Test get_credit_cards_with_debt function."""

    def test_filters_credit_cards_with_negative_balance(self):
        """Test filtering credit cards with debt."""
        # Arrange
        accounts = [
            YNABAccount(
                name="Credit Card 1",
                balance=Decimal("-1500.00"),
                account_type="credit_card",
                budget_id="main",
                consolidated=True,
                payment_due_date=15,
            ),
            YNABAccount(
                name="Checking Account",
                balance=Decimal("3000.00"),
                account_type="checking",
                budget_id="main",
                consolidated=True,
                payment_due_date=None,
            ),
            YNABAccount(
                name="Credit Card 2",
                balance=Decimal("100.00"),  # Positive balance
                account_type="credit_card",
                budget_id="main",
                consolidated=True,
                payment_due_date=20,
            ),
            YNABAccount(
                name="Credit Card 3",
                balance=Decimal("-2500.00"),
                account_type="credit_card",
                budget_id="secondary",
                consolidated=True,
                payment_due_date=25,
            ),
        ]

        # Act
        result = get_credit_cards_with_debt(accounts)

        # Assert
        assert len(result) == 2
        assert result[0]["name"] == "Credit Card 1"
        assert result[1]["name"] == "Credit Card 3"
        assert all(account["account_type"] == "credit_card" for account in result)
        assert all(account["balance"] < 0 for account in result)


class TestGetDebitSourcesWithFunds:
    """Test get_debit_sources_with_funds function."""

    def test_filters_debit_accounts_with_positive_balance(self):
        """Test filtering debit accounts with funds."""
        # Arrange
        accounts = [
            YNABAccount(
                name="Main Checking",
                balance=Decimal("3000.00"),
                account_type="checking",
                budget_id="main",
                consolidated=True,
                payment_due_date=None,
            ),
            YNABAccount(
                name="Credit Card",
                balance=Decimal("-1500.00"),
                account_type="credit_card",
                budget_id="main",
                consolidated=True,
                payment_due_date=15,
            ),
            YNABAccount(
                name="Empty Checking",
                balance=Decimal("0.00"),
                account_type="checking",
                budget_id="main",
                consolidated=True,
                payment_due_date=None,
            ),
            YNABAccount(
                name="Investment Savings",
                balance=Decimal("10000.00"),
                account_type="savings",
                budget_id="secondary",
                consolidated=True,
                payment_due_date=None,
            ),
        ]

        # Act
        result = get_debit_sources_with_funds(accounts)

        # Assert
        assert len(result) == 2
        assert result[0]["name"] == "Main Checking"
        assert result[1]["name"] == "Investment Savings"
        assert all(
            account["account_type"] in ("checking", "savings") for account in result
        )
        assert all(account["balance"] > 0 for account in result)

    def test_filters_by_budget_id(self):
        """Test filtering debit accounts by budget ID."""
        # Arrange
        accounts = [
            YNABAccount(
                name="Main Checking",
                balance=Decimal("3000.00"),
                account_type="checking",
                budget_id="main",
                consolidated=True,
                payment_due_date=None,
            ),
            YNABAccount(
                name="Secondary Checking",
                balance=Decimal("5000.00"),
                account_type="checking",
                budget_id="secondary",
                consolidated=True,
                payment_due_date=None,
            ),
        ]

        # Act
        result = get_debit_sources_with_funds(accounts, budget_id="main")

        # Assert
        assert len(result) == 1
        assert result[0]["name"] == "Main Checking"
        assert result[0]["budget_id"] == "main"

    def test_returns_all_when_no_budget_filter(self):
        """Test that all accounts are returned when no budget filter is applied."""
        # Arrange
        accounts = [
            YNABAccount(
                name="Main Checking",
                balance=Decimal("3000.00"),
                account_type="checking",
                budget_id="main",
                consolidated=True,
                payment_due_date=None,
            ),
            YNABAccount(
                name="Secondary Checking",
                balance=Decimal("5000.00"),
                account_type="checking",
                budget_id="secondary",
                consolidated=True,
                payment_due_date=None,
            ),
        ]

        # Act
        result = get_debit_sources_with_funds(accounts, budget_id=None)

        # Assert
        assert len(result) == 2
