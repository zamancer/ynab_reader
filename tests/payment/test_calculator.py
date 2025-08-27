from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.payment.calculator import (
    PaymentCalculator,
    PaymentCalculatorError,
    SimpleRuleEngine,
)
from src.payment.config import PaymentConfigLoader
from src.payment.strategies.base_strategy import PaymentStrategy
from src.ynab.ynab_types import (
    PaymentConfig,
    PaymentRule,
    YNABAccount,
)


class TestPaymentCalculator:
    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Mock config loader
        self.mock_config_loader = Mock(spec=PaymentConfigLoader)

        # Test payment configuration
        self.test_config: PaymentConfig = {
            "default_payment_sources": {
                "main": ["Main Checking", "Main Savings"],
                "secondary": ["Investment Checking"],
            },
            "payment_rules": [
                {
                    "credit_card_name": "Chase Sapphire",
                    "budget_id": "main",
                    "debit_sources": ["Main Checking", "Main Savings"],
                    "strategy": "priority_ordered",
                    "strategy_config": {"min_balance": 100},
                    "rule_origin": "explicit",
                }
            ],
            "global_strategy_defaults": {"priority_ordered": {"min_balance": 50}},
        }
        self.mock_config_loader.load_config.return_value = self.test_config

        # Test accounts
        self.credit_cards = [
            {
                "name": "Chase Sapphire",
                "balance": Decimal("-1000.00"),
                "account_type": "credit_card",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": 15,
            },
            {
                "name": "No Debt Card",
                "balance": Decimal("0"),
                "account_type": "credit_card",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": 20,
            },
        ]

        self.available_funds = [
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

        # Create calculator instance
        self.calculator = PaymentCalculator(self.mock_config_loader)

    def test_calculate_payments_success_single_card(self):
        """Test successful calculation for single credit card with debt."""
        # Act
        instructions = self.calculator.calculate_payments(
            self.credit_cards, self.available_funds
        )

        # Assert
        assert len(instructions) == 1
        instruction = instructions[0]
        assert instruction["credit_card"] == "Chase Sapphire"
        assert instruction["payment_amount"] == Decimal("1000.00")
        assert instruction["remaining_balance"] == Decimal("0")
        self.mock_config_loader.load_config.assert_called_once()

    def test_calculate_payments_no_debt_cards_returns_empty(self):
        """Test that accounts with no debt return no instructions."""
        # Arrange
        no_debt_cards = [
            card for card in self.credit_cards if card["balance"] >= Decimal("0")
        ]

        # Act
        instructions = self.calculator.calculate_payments(
            no_debt_cards, self.available_funds
        )

        # Assert
        assert instructions == []

    def test_calculate_payments_multiple_cards_sorted_by_urgency(self):
        """Test multiple cards are processed and sorted by urgency."""
        # Arrange
        multiple_cards = self.credit_cards + [
            {
                "name": "Urgent Card",
                "balance": Decimal("-500.00"),
                "account_type": "credit_card",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": 10,  # More urgent (lower days until due)
            }
        ]

        # Act
        instructions = self.calculator.calculate_payments(
            multiple_cards, self.available_funds
        )

        # Assert
        assert len(instructions) >= 2
        # Instructions should be sorted by urgency (days_until_due ascending)
        days_until_due = [inst["days_until_due"] for inst in instructions]
        assert days_until_due == sorted(days_until_due)

    def test_calculate_payments_no_available_sources_skips_card(self):
        """Test that cards with no available payment sources are skipped."""
        # Arrange
        empty_funds = []  # No available funds

        # Act
        instructions = self.calculator.calculate_payments(
            self.credit_cards, empty_funds
        )

        # Assert
        assert instructions == []

    def test_calculate_payments_config_loading_failure(self):
        """Test error handling when config loading fails."""
        # Arrange
        self.mock_config_loader.load_config.side_effect = Exception("Config load error")

        # Act & Assert
        with pytest.raises(PaymentCalculatorError, match="Payment calculation failed"):
            self.calculator.calculate_payments(self.credit_cards, self.available_funds)

    def test_calculate_payments_continues_on_individual_card_failure(self):
        """Test that failure for one card doesn't stop processing others."""
        # Arrange
        # Create a card that will cause strategy failure
        problematic_card = {
            "name": "Problem Card",
            "balance": Decimal("-500.00"),
            "account_type": "credit_card",
            "budget_id": "nonexistent_budget",  # No rule for this budget
            "consolidated": True,
            "payment_due_date": 25,
        }
        mixed_cards = self.credit_cards + [problematic_card]

        # Act
        instructions = self.calculator.calculate_payments(
            mixed_cards, self.available_funds
        )

        # Assert
        # Should still process the valid card despite the problematic one
        assert len(instructions) >= 1
        assert any(inst["credit_card"] == "Chase Sapphire" for inst in instructions)

    def test_register_strategy(self):
        """Test registering a new payment strategy."""
        # Arrange
        mock_strategy = Mock(spec=PaymentStrategy)

        # Act
        self.calculator.register_strategy("test_strategy", mock_strategy)

        # Assert
        assert "test_strategy" in self.calculator.get_available_strategies()

    def test_get_available_strategies(self):
        """Test getting list of available strategies."""
        # Act
        strategies = self.calculator.get_available_strategies()

        # Assert
        assert "priority_ordered" in strategies
        assert isinstance(strategies, list)

    def test_create_strategy_unknown_strategy_raises_error(self):
        """Test that creating unknown strategy raises error."""
        # Act & Assert
        with pytest.raises(PaymentCalculatorError, match="Unknown payment strategy"):
            self.calculator._create_strategy("nonexistent_strategy")

    def test_merge_strategy_config_with_global_defaults(self):
        """Test strategy config merging with global defaults."""
        # Arrange
        rule: PaymentRule = {
            "credit_card_name": "Test Card",
            "budget_id": "main",
            "debit_sources": ["Test Source"],
            "strategy": "priority_ordered",
            "strategy_config": {"max_payment_per_source": 500},
            "rule_origin": "explicit",
        }

        # Act
        merged_config = self.calculator._merge_strategy_config(
            rule, self.test_config, "priority_ordered"
        )

        # Assert
        assert merged_config["min_balance"] == 50  # From global defaults
        assert merged_config["max_payment_per_source"] == 500  # From rule config

    def test_merge_strategy_config_rule_overrides_global(self):
        """Test that rule config overrides global defaults."""
        # Arrange
        rule: PaymentRule = {
            "credit_card_name": "Test Card",
            "budget_id": "main",
            "debit_sources": ["Test Source"],
            "strategy": "priority_ordered",
            "strategy_config": {"min_balance": 200},  # Override global default
            "rule_origin": "explicit",
        }

        # Act
        merged_config = self.calculator._merge_strategy_config(
            rule, self.test_config, "priority_ordered"
        )

        # Assert
        assert merged_config["min_balance"] == 200  # Rule override

    def test_get_available_sources_filters_positive_balances(self):
        """Test that only sources with positive balance are returned."""
        # Arrange
        mixed_funds = self.available_funds + [
            {
                "name": "Empty Account",
                "balance": Decimal("0"),
                "account_type": "checking",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": None,
            }
        ]
        credit_card = self.credit_cards[0]

        # Act
        available_sources = self.calculator._get_available_sources(
            credit_card, mixed_funds
        )

        # Assert
        assert len(available_sources) == 2  # Only accounts with positive balance
        assert all(source["balance"] > Decimal("0") for source in available_sources)


class TestSimpleRuleEngine:
    def setup_method(self):
        """Set up test fixtures for rule engine tests."""
        self.rule_engine = SimpleRuleEngine()
        self.test_config: PaymentConfig = {
            "default_payment_sources": {
                "main": ["Main Checking", "Main Savings"],
                "secondary": ["Investment Checking"],
            },
            "payment_rules": [
                {
                    "credit_card_name": "Chase Sapphire",
                    "budget_id": "main",
                    "debit_sources": ["Main Checking", "Emergency Fund"],
                    "strategy": "priority_ordered",
                    "strategy_config": {"min_balance": 100},
                }
            ],
            "global_strategy_defaults": None,
        }

    def test_get_payment_rule_explicit_rule_found(self):
        """Test finding explicit rule for credit card."""
        # Arrange
        credit_card: YNABAccount = {
            "name": "Chase Sapphire",
            "balance": Decimal("-1000.00"),
            "account_type": "credit_card",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": 15,
        }

        # Act
        rule = self.rule_engine.get_payment_rule(credit_card, self.test_config)

        # Assert
        assert rule["credit_card_name"] == "Chase Sapphire"
        assert rule["budget_id"] == "main"
        assert rule["debit_sources"] == ["Main Checking", "Emergency Fund"]
        assert rule["strategy"] == "priority_ordered"
        assert rule["rule_origin"] == "explicit"

    def test_get_payment_rule_uses_default_sources(self):
        """Test using default sources when no explicit rule found."""
        # Arrange
        credit_card: YNABAccount = {
            "name": "Unknown Card",
            "balance": Decimal("-500.00"),
            "account_type": "credit_card",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": 20,
        }

        # Act
        rule = self.rule_engine.get_payment_rule(credit_card, self.test_config)

        # Assert
        assert rule["credit_card_name"] == "Unknown Card"
        assert rule["budget_id"] == "main"
        assert rule["debit_sources"] == [
            "Main Checking",
            "Main Savings",
        ]  # From defaults
        assert rule["strategy"] is None  # Default strategy
        assert rule["rule_origin"] == "default"

    def test_get_payment_rule_no_rule_or_default_raises_error(self):
        """Test error when no rule or default sources exist for budget."""
        # Arrange
        credit_card: YNABAccount = {
            "name": "Orphan Card",
            "balance": Decimal("-300.00"),
            "account_type": "credit_card",
            "budget_id": "nonexistent_budget",
            "consolidated": True,
            "payment_due_date": 25,
        }

        # Act & Assert
        with pytest.raises(
            PaymentCalculatorError, match="No payment rule or default sources found"
        ):
            self.rule_engine.get_payment_rule(credit_card, self.test_config)

    def test_get_payment_rule_handles_budget_specific_matching(self):
        """Test that rule matching considers both card name and budget ID."""
        # Arrange
        # Add rule for same card name but different budget
        self.test_config["payment_rules"].append(
            {
                "credit_card_name": "Chase Sapphire",
                "budget_id": "secondary",
                "debit_sources": ["Investment Checking"],
                "strategy": None,
                "strategy_config": None,
            }
        )

        credit_card: YNABAccount = {
            "name": "Chase Sapphire",
            "balance": Decimal("-800.00"),
            "account_type": "credit_card",
            "budget_id": "secondary",  # Different budget
            "consolidated": True,
            "payment_due_date": 10,
        }

        # Act
        rule = self.rule_engine.get_payment_rule(credit_card, self.test_config)

        # Assert
        assert rule["budget_id"] == "secondary"
        assert rule["debit_sources"] == ["Investment Checking"]  # Secondary budget rule

    def test_get_payment_rule_does_not_mutate_original_config(self):
        """Test that getting a rule doesn't mutate the original configuration."""
        # Arrange
        original_rules_count = len(self.test_config["payment_rules"])
        original_rule = self.test_config["payment_rules"][0].copy()

        credit_card: YNABAccount = {
            "name": "Chase Sapphire",
            "balance": Decimal("-1000.00"),
            "account_type": "credit_card",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": 15,
        }

        # Act
        rule = self.rule_engine.get_payment_rule(credit_card, self.test_config)

        # Assert
        # Original config should be unchanged
        assert len(self.test_config["payment_rules"]) == original_rules_count
        assert self.test_config["payment_rules"][0] == original_rule
        # Original rule should not have rule_origin field
        assert "rule_origin" not in self.test_config["payment_rules"][0]
        # But returned rule should have it
        assert rule["rule_origin"] == "explicit"

    def test_get_payment_rule_default_sources_not_mutated(self):
        """Test that default rule creation doesn't mutate the original default_payment_sources."""
        # Arrange
        original_default_sources = self.test_config["default_payment_sources"][
            "main"
        ].copy()

        credit_card: YNABAccount = {
            "name": "Unknown Card",
            "balance": Decimal("-500.00"),
            "account_type": "credit_card",
            "budget_id": "main",
            "consolidated": True,
            "payment_due_date": 20,
        }

        # Act
        rule = self.rule_engine.get_payment_rule(credit_card, self.test_config)
        rule["debit_sources"].append("Modified Source")  # Try to modify returned rule

        # Assert
        # Original default sources should be unchanged
        assert (
            self.test_config["default_payment_sources"]["main"]
            == original_default_sources
        )
        # The returned rule should have its own copy
        assert (
            rule["debit_sources"] != self.test_config["default_payment_sources"]["main"]
        )
