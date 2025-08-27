"""
Base strategy interface for payment calculations.
Defines the contract for payment strategies.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.ynab.ynab_types import PaymentInstruction, PaymentRule, YNABAccount


class PaymentStrategy(ABC):
    """Abstract base class for payment strategies."""

    @abstractmethod
    def calculate_payments(
        self,
        credit_card: YNABAccount,
        available_sources: list[YNABAccount],
        rule: PaymentRule,
        strategy_config: dict[str, Any],
    ) -> list[PaymentInstruction]:
        """
        Calculate how to pay a credit card using available sources.

        Args:
            credit_card: The credit card account with negative balance to pay
            available_sources: List of debit accounts available for payment
            rule: Payment rule containing debit source priorities and config
            strategy_config: Strategy-specific configuration parameters

        Returns:
            List of PaymentInstruction objects representing individual transfers

        Raises:
            PaymentStrategyError: If payment calculation fails
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return strategy identifier for logging and configuration."""
        pass

    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate strategy-specific configuration.

        Args:
            config: Strategy configuration dictionary

        Returns:
            True if configuration is valid

        Raises:
            ConfigurationError: If configuration is invalid
        """
        return True


class PaymentStrategyError(Exception):
    """Raised when payment strategy calculation fails."""

    pass
