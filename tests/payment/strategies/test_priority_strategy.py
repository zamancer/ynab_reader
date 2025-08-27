from decimal import Decimal
from unittest.mock import patch

import pytest

from src.payment.strategies.base_strategy import PaymentStrategyError
from src.payment.strategies.priority_strategy import PriorityOrderedStrategy
from src.ynab.ynab_types import PaymentRule, YNABAccount


class TestPriorityOrderedStrategy:
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.strategy = PriorityOrderedStrategy()

        # Common test credit card
        self.credit_card: YNABAccount = {
            "name": "Chase Sapphire",
            "balance": Decimal("-1000.00"),
            "account_type": "credit_card",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": 15,
        }

        # Common test debit sources
        self.debit_sources = [
            {
                "name": "Main Checking",
                "balance": Decimal("2000.00"),
                "account_type": "checking",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": None,
            },
            {
                "name": "Main Savings",
                "balance": Decimal("5000.00"),
                "account_type": "savings",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": None,
            },
        ]

        # Common test rule
        self.payment_rule: PaymentRule = {
            "credit_card_name": "Chase Sapphire",
            "budget_id": "main",
            "debit_sources": ["Main Checking", "Main Savings"],
            "strategy": "priority_ordered",
            "strategy_config": {"min_balance": 100},
            "rule_origin": "explicit",
        }

    def test_calculate_payments_success_single_source(self):
        """Test successful payment from single source with sufficient funds."""
        # Arrange
        strategy_config = {"min_balance": 100}

        # Act
        instructions = self.strategy.calculate_payments(
            self.credit_card, self.debit_sources, self.payment_rule, strategy_config
        )

        # Assert
        assert len(instructions) == 1
        instruction = instructions[0]
        assert instruction["credit_card"] == "Chase Sapphire"
        assert instruction["payment_source"] == "Main Checking"
        assert instruction["payment_amount"] == Decimal("1000.00")
        assert instruction["remaining_balance"] == Decimal("0")
        assert instruction["rule_type"] == "explicit"
        assert instruction["strategy_used"] == "priority_ordered"

    def test_calculate_payments_multiple_sources_required(self):
        """Test payment requiring multiple sources due to insufficient balance in first source."""
        # Arrange
        # Reduce first source balance to require second source
        limited_sources = self.debit_sources.copy()
        limited_sources[0]["balance"] = Decimal(
            "600.00"
        )  # Only 500 available after min_balance
        strategy_config = {"min_balance": 100}

        # Act
        instructions = self.strategy.calculate_payments(
            self.credit_card, limited_sources, self.payment_rule, strategy_config
        )

        # Assert
        assert len(instructions) == 2

        # First transfer from Main Checking
        assert instructions[0]["payment_source"] == "Main Checking"
        assert instructions[0]["payment_amount"] == Decimal("500.00")
        assert instructions[0]["remaining_balance"] == Decimal("500.00")
        assert (
            instructions[0]["notes"]
            == "Transfer 1 of 2 - ALERTA: Saldo restante $500.00"
        )

        # Second transfer from Main Savings
        assert instructions[1]["payment_source"] == "Main Savings"
        assert instructions[1]["payment_amount"] == Decimal("500.00")
        assert instructions[1]["remaining_balance"] == Decimal("0")
        assert instructions[1]["notes"] == "Transfer 2 of 2"

    def test_calculate_payments_partial_payment_insufficient_funds(self):
        """Test partial payment when total available funds are insufficient."""
        # Arrange
        insufficient_sources = [
            {
                "name": "Main Checking",
                "balance": Decimal("300.00"),
                "account_type": "checking",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": None,
            }
        ]
        strategy_config = {"min_balance": 100}

        # Act
        instructions = self.strategy.calculate_payments(
            self.credit_card, insufficient_sources, self.payment_rule, strategy_config
        )

        # Assert
        assert len(instructions) == 1
        instruction = instructions[0]
        assert instruction["payment_amount"] == Decimal(
            "200.00"
        )  # 300 - 100 min_balance
        assert instruction["remaining_balance"] == Decimal("800.00")  # 1000 - 200
        assert "PAGO PARCIAL: Fondos insuficientes" in instruction["notes"]

    def test_calculate_payments_no_debt_returns_empty(self):
        """Test that credit card with no debt returns no instructions."""
        # Arrange
        no_debt_card = self.credit_card.copy()
        no_debt_card["balance"] = Decimal("0")

        # Act
        instructions = self.strategy.calculate_payments(
            no_debt_card, self.debit_sources, self.payment_rule, {}
        )

        # Assert
        assert instructions == []

    def test_calculate_payments_with_max_payment_constraint(self):
        """Test payment respects max_payment_per_source constraint."""
        # Arrange
        strategy_config = {"min_balance": 100, "max_payment_per_source": 300}

        # Act
        instructions = self.strategy.calculate_payments(
            self.credit_card, self.debit_sources, self.payment_rule, strategy_config
        )

        # Assert
        assert len(instructions) == 2
        # First source limited by max_payment_per_source
        assert instructions[0]["payment_amount"] == Decimal("300.00")
        # Second source also limited by max_payment_per_source (constraint applies to each source)
        assert instructions[1]["payment_amount"] == Decimal("300.00")
        # Verify partial payment (400 remaining: 1000 - 300 - 300)
        assert instructions[1]["remaining_balance"] == Decimal("400.00")

    @patch("src.payment.strategies.priority_strategy.datetime")
    def test_calculate_payments_calculates_days_until_due(self, mock_datetime):
        """Test that days until due date is calculated correctly."""
        # Arrange
        mock_datetime.now.return_value.day = 10  # Today is 10th
        strategy_config = {"min_balance": 100}

        # Act
        instructions = self.strategy.calculate_payments(
            self.credit_card, self.debit_sources, self.payment_rule, strategy_config
        )

        # Assert
        assert instructions[0]["days_until_due"] == 5  # 15 - 10

    def test_calculate_payments_error_handling(self):
        """Test error handling when calculation fails."""
        # Arrange
        invalid_sources = [{"invalid": "source"}]  # Missing required fields

        # Act & Assert
        with pytest.raises(
            PaymentStrategyError, match="Priority strategy calculation failed"
        ):
            self.strategy.calculate_payments(
                self.credit_card, invalid_sources, self.payment_rule, {}
            )

    def test_get_strategy_name(self):
        """Test strategy name is returned correctly."""
        # Act & Assert
        assert self.strategy.get_strategy_name() == "priority_ordered"

    def test_validate_config_success(self):
        """Test configuration validation with valid config."""
        # Arrange
        valid_config = {"min_balance": 100, "max_payment_per_source": 1000}

        # Act
        result = self.strategy.validate_config(valid_config)

        # Assert
        assert result is True

    def test_validate_config_invalid_min_balance(self):
        """Test configuration validation with invalid min_balance."""
        # Arrange
        invalid_config = {"min_balance": -100}

        # Act & Assert
        with pytest.raises(
            PaymentStrategyError, match="min_balance must be non-negative number"
        ):
            self.strategy.validate_config(invalid_config)

    def test_validate_config_invalid_max_payment(self):
        """Test configuration validation with invalid max_payment_per_source."""
        # Arrange
        invalid_config = {"max_payment_per_source": 0}

        # Act & Assert
        with pytest.raises(
            PaymentStrategyError, match="max_payment_per_source must be positive number"
        ):
            self.strategy.validate_config(invalid_config)

    def test_sort_by_priority_maintains_order(self):
        """Test that sources are sorted according to priority list."""
        # Arrange
        priority_list = ["Main Savings", "Main Checking"]

        # Act
        sorted_sources = self.strategy._sort_by_priority(
            self.debit_sources, priority_list
        )

        # Assert
        assert len(sorted_sources) == 2
        assert sorted_sources[0]["name"] == "Main Savings"  # Higher priority
        assert sorted_sources[1]["name"] == "Main Checking"

    def test_sort_by_priority_adds_unlisted_sources(self):
        """Test that sources not in priority list are added as fallback."""
        # Arrange
        extra_source = {
            "name": "Emergency Fund",
            "balance": Decimal("1000.00"),
            "account_type": "savings",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": None,
        }
        all_sources = self.debit_sources + [extra_source]
        priority_list = ["Main Checking"]  # Only one source prioritized

        # Act
        sorted_sources = self.strategy._sort_by_priority(all_sources, priority_list)

        # Assert
        assert len(sorted_sources) == 3
        assert sorted_sources[0]["name"] == "Main Checking"  # Prioritized first
        # Other sources added as fallback
        remaining_names = {s["name"] for s in sorted_sources[1:]}
        assert remaining_names == {"Main Savings", "Emergency Fund"}

    def test_create_payment_instruction_with_due_date_none(self):
        """Test payment instruction creation when due date is None."""
        # Arrange
        card_no_due = self.credit_card.copy()
        card_no_due["payment_due_date"] = None
        source = self.debit_sources[0]

        # Act
        instruction = self.strategy._create_payment_instruction(
            credit_card=card_no_due,
            source=source,
            payment_amount=Decimal("500.00"),
            remaining_debt=Decimal("500.00"),
            target_amount=Decimal("1000.00"),
            transfer_number=1,
            total_transfers=2,
            rule=self.payment_rule,
        )

        # Assert
        assert instruction["days_until_due"] == 0
        assert instruction["payment_due_date"] is None

    def test_create_payment_instruction_multiple_transfer_notes(self):
        """Test note generation for multiple transfer scenarios."""
        # Arrange
        source = self.debit_sources[0]

        # Act
        instruction = self.strategy._create_payment_instruction(
            credit_card=self.credit_card,
            source=source,
            payment_amount=Decimal("600.00"),
            remaining_debt=Decimal("400.00"),  # Still debt remaining
            target_amount=Decimal("1000.00"),
            transfer_number=1,
            total_transfers=2,
            rule=self.payment_rule,
        )

        # Assert
        expected_notes = "Transfer 1 of 2 - ALERTA: Saldo restante $400.00"
        assert instruction["notes"] == expected_notes
