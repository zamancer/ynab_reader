"""
Payment calculator orchestrating the payment calculation process.
Handles payment orchestration only.
"""

import copy
import logging
from decimal import Decimal
from typing import Any, Protocol

from src.payment.config import PaymentConfigLoader
from src.payment.strategies.base_strategy import PaymentStrategy
from src.payment.strategies.priority_strategy import PriorityOrderedStrategy
from src.ynab.ynab_types import (
    PaymentConfig,
    PaymentInstruction,
    PaymentRule,
    YNABAccount,
)

logger = logging.getLogger(__name__)


class RuleEngine(Protocol):
    """Protocol for payment rule engine."""

    def get_payment_rule(
        self, credit_card: YNABAccount, config: PaymentConfig
    ) -> PaymentRule:
        """Get payment rule for a credit card."""
        ...


class SimpleRuleEngine:
    """Simple rule engine that matches credit cards to payment rules."""

    def get_payment_rule(
        self, credit_card: YNABAccount, config: PaymentConfig
    ) -> PaymentRule:
        """
        Get payment rule for a credit card.

        Args:
            credit_card: Credit card account to find rule for
            config: Payment configuration containing rules and defaults

        Returns:
            PaymentRule: Rule for paying this credit card (explicit or default)

        Raises:
            PaymentCalculatorError: If no rule can be determined
        """
        try:
            # Look for explicit rule matching credit card name + budget ID
            for rule in config["payment_rules"]:
                if (
                    rule["credit_card_name"] == credit_card["name"]
                    and rule["budget_id"] == credit_card["budget_id"]
                ):
                    logger.debug(f"Found explicit rule for {credit_card['name']}")
                    # Return a copy with rule_origin to avoid mutating original config
                    explicit_rule = copy.deepcopy(rule)
                    explicit_rule["rule_origin"] = "explicit"
                    return explicit_rule

            # Use default sources for the budget
            budget_id = credit_card["budget_id"]
            default_sources = config["default_payment_sources"].get(budget_id)
            if not default_sources:
                raise PaymentCalculatorError(
                    f"No payment rule or default sources found for credit card "
                    f"{credit_card['name']} in budget {budget_id}"
                )

            # Create default rule (already a new dict, no mutation concern)
            default_rule: PaymentRule = {
                "credit_card_name": credit_card["name"],
                "budget_id": budget_id,
                "debit_sources": list(default_sources),  # Create copy to avoid mutation
                "strategy": None,  # Will use default strategy
                "strategy_config": None,
                "rule_origin": "default",
            }
            logger.debug(f"Using default rule for {credit_card['name']}")
            return default_rule

        except Exception as e:
            raise PaymentCalculatorError(
                f"Failed to determine payment rule: {e}"
            ) from e


class PaymentCalculator:
    """
    Main payment calculator orchestrating the payment calculation process.

    Follows the Strategy pattern to support different payment calculation strategies.
    Uses dependency injection for testability.
    """

    def __init__(
        self,
        config_loader: PaymentConfigLoader,
        rule_engine: RuleEngine | None = None,
        logger_instance: logging.Logger | None = None,
    ):
        """
        Initialize payment calculator.

        Args:
            config_loader: Configuration loader for payment rules
            rule_engine: Rule engine for matching cards to rules (optional)
            logger_instance: Logger instance (optional)
        """
        self.config_loader = config_loader
        self.rule_engine = rule_engine or SimpleRuleEngine()
        self.logger = logger_instance or logger
        self._strategy_registry: dict[str, type[PaymentStrategy]] = {
            "priority_ordered": PriorityOrderedStrategy,
        }

    def calculate_payments(
        self, credit_cards: list[YNABAccount], available_funds: list[YNABAccount]
    ) -> list[PaymentInstruction]:
        """
        Calculate payment instructions for all credit cards with debt.

        Args:
            credit_cards: List of credit card accounts (should include cards with negative balances)
            available_funds: List of debit accounts available for payments

        Returns:
            List of PaymentInstructions ordered by urgency (due date)

        Raises:
            PaymentCalculatorError: If calculation fails
        """
        try:
            # Load configuration
            config = self.config_loader.load_config()
            self.logger.info(
                f"Loaded payment configuration with {len(config['payment_rules'])} rules"
            )

            # Filter credit cards with debt (negative balance)
            cards_with_debt = [
                card for card in credit_cards if card["balance"] < Decimal("0")
            ]
            if not cards_with_debt:
                self.logger.info("No credit cards with debt found")
                return []

            self.logger.info(
                f"Processing {len(cards_with_debt)} credit cards with debt"
            )

            all_instructions: list[PaymentInstruction] = []

            for card in cards_with_debt:
                try:
                    # Get payment rule for this card
                    rule = self.rule_engine.get_payment_rule(card, config)

                    # Get available sources for this card's budget
                    available_sources = self._get_available_sources(
                        card, available_funds
                    )
                    if not available_sources:
                        self.logger.warning(
                            f"No payment sources available for {card['name']}"
                        )
                        continue

                    # Determine strategy and configuration
                    strategy_name = rule.get("strategy") or "priority_ordered"
                    strategy_config = self._merge_strategy_config(
                        rule, config, strategy_name
                    )

                    # Create strategy instance and validate configuration
                    strategy = self._create_strategy(strategy_name)
                    strategy.validate_config(strategy_config)
                    instructions = strategy.calculate_payments(
                        card, available_sources, rule, strategy_config
                    )

                    all_instructions.extend(instructions)
                    self.logger.info(
                        f"Generated {len(instructions)} instructions for {card['name']}"
                    )

                except Exception as e:
                    self.logger.error(
                        f"Failed to calculate payments for {card.get('name', 'unknown')}: {e}"
                    )
                    # Continue with other cards rather than failing completely
                    continue

            # Sort by urgency (days until due date, most urgent first)
            sorted_instructions = sorted(
                all_instructions, key=lambda x: x["days_until_due"]
            )

            self.logger.info(
                f"Generated {len(sorted_instructions)} total payment instructions"
            )
            return sorted_instructions

        except Exception as e:
            self.logger.error(f"Payment calculation failed: {e}")
            raise PaymentCalculatorError(f"Payment calculation failed: {e}") from e

    def _get_available_sources(
        self, credit_card: YNABAccount, available_funds: list[YNABAccount]
    ) -> list[YNABAccount]:
        """
        Get available payment sources for a credit card based on its budget.

        Args:
            credit_card: Credit card account
            available_funds: All available debit accounts

        Returns:
            List of debit accounts available for this card's budget
        """
        # For now, return all available funds regardless of budget
        # TODO: In the future, we might want to filter by budget constraints
        return [fund for fund in available_funds if fund["balance"] > Decimal("0")]

    def _merge_strategy_config(
        self, rule: PaymentRule, config: PaymentConfig, strategy_name: str
    ) -> dict[str, Any]:
        """
        Merge rule-specific config with global strategy defaults.

        Args:
            rule: Payment rule for the credit card
            config: Global payment configuration
            strategy_name: Name of the strategy being used

        Returns:
            Merged configuration dictionary
        """
        merged_config: dict[str, Any] = {}

        # Start with global defaults for this strategy
        global_defaults = config.get("global_strategy_defaults", {})
        if global_defaults and strategy_name in global_defaults:
            merged_config.update(global_defaults[strategy_name])

        # Override with rule-specific config
        rule_config = rule.get("strategy_config")
        if rule_config:
            merged_config.update(rule_config)

        return merged_config

    def _create_strategy(self, strategy_name: str) -> PaymentStrategy:
        """
        Create strategy instance by name.

        Args:
            strategy_name: Name of the strategy to create

        Returns:
            PaymentStrategy instance

        Raises:
            PaymentCalculatorError: If strategy is not found
        """
        if strategy_name not in self._strategy_registry:
            raise PaymentCalculatorError(f"Unknown payment strategy: {strategy_name}")

        strategy_class = self._strategy_registry[strategy_name]
        return strategy_class()

    def register_strategy(
        self, name: str, strategy_class: type[PaymentStrategy]
    ) -> None:
        """
        Register a new payment strategy.

        Args:
            name: Strategy name
            strategy_class: Strategy class to register
        """
        self._strategy_registry[name] = strategy_class
        self.logger.info(f"Registered payment strategy: {name}")

    def get_available_strategies(self) -> list[str]:
        """Get list of available strategy names."""
        return list(self._strategy_registry.keys())


class PaymentCalculatorError(Exception):
    """Raised when payment calculation fails."""

    pass
