"""
Configuration management for payment feature.
Handles payment configuration loading and validation.
"""

import json
import logging
import os
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Protocol

from src.ynab.ynab_types import PaymentConfig

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class PaymentConfigLoader(Protocol):
    """Protocol for payment configuration loading."""

    def load_config(self) -> PaymentConfig:
        """Load payment configuration from source."""
        ...


class JsonPaymentConfigLoader:
    """Loads payment configuration from JSON file."""

    def __init__(self, config_path: str | Path):
        """Initialize with configuration file path."""
        self.config_path = Path(config_path)

    def load_config(self) -> PaymentConfig:
        """
        Load and validate payment configuration from JSON file.

        Returns:
            PaymentConfig: Validated configuration object

        Raises:
            ConfigurationError: If configuration is invalid or cannot be loaded
        """
        try:
            if (not self.config_path.exists()) or (not self.config_path.is_file()):
                raise ConfigurationError(
                    f"Configuration file not found or is not a file: {self.config_path}"
                )

            with open(self.config_path, encoding="utf-8") as file:
                raw_config = json.load(file, parse_float=Decimal)

            validated_config = self._validate_config(raw_config)
            logger.info(
                f"Successfully loaded payment configuration from {self.config_path}"
            )

            return validated_config

        except ConfigurationError:
            raise
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}") from e
        except OSError as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e

    def _validate_config(self, config: dict) -> PaymentConfig:
        """
        Validate configuration structure and required fields.

        Args:
            config: Raw configuration dictionary

        Returns:
            PaymentConfig: Validated configuration object

        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            # Validate required top-level keys
            required_keys = {"default_payment_sources", "payment_rules"}
            missing_keys = required_keys - set(config.keys())
            if missing_keys:
                raise ConfigurationError(
                    f"Missing required configuration keys: {missing_keys}"
                )

            # Validate default_payment_sources structure
            default_sources = config["default_payment_sources"]
            if not isinstance(default_sources, dict):
                raise ConfigurationError("default_payment_sources must be a dictionary")

            for budget_id, sources in default_sources.items():
                if not isinstance(budget_id, str):
                    raise ConfigurationError(
                        f"Budget ID must be string, got: {type(budget_id)}"
                    )
                if not isinstance(sources, list):
                    raise ConfigurationError(
                        f"Payment sources must be list, got: {type(sources)}"
                    )
                if not all(isinstance(source, str) for source in sources):
                    raise ConfigurationError(
                        f"All payment sources must be strings for budget: {budget_id}"
                    )

            # Validate payment_rules structure
            payment_rules = config["payment_rules"]
            if not isinstance(payment_rules, list):
                raise ConfigurationError("payment_rules must be a list")

            for i, rule in enumerate(payment_rules):
                self._validate_payment_rule(rule, i)

            # Validate optional global_strategy_defaults
            global_defaults = config.get("global_strategy_defaults")
            if global_defaults is not None:
                if not isinstance(global_defaults, dict):
                    raise ConfigurationError(
                        "global_strategy_defaults must be a dictionary"
                    )

            return PaymentConfig(
                default_payment_sources=default_sources,
                payment_rules=payment_rules,
                global_strategy_defaults=global_defaults,
            )

        except KeyError as e:
            raise ConfigurationError(f"Missing configuration key: {e}") from e

    def _validate_payment_rule(self, rule: dict, rule_index: int) -> None:
        """
        Validate individual payment rule structure.

        Args:
            rule: Payment rule dictionary
            rule_index: Index of rule for error reporting

        Raises:
            ConfigurationError: If rule is invalid
        """
        required_fields = {"credit_card_name", "budget_id", "debit_sources"}
        missing_fields = required_fields - set(rule.keys())
        if missing_fields:
            raise ConfigurationError(
                f"Payment rule {rule_index} missing required fields: {missing_fields}"
            )

        # Validate field types
        if not isinstance(rule["credit_card_name"], str):
            raise ConfigurationError(
                f"Payment rule {rule_index}: credit_card_name must be string"
            )

        if not isinstance(rule["budget_id"], str):
            raise ConfigurationError(
                f"Payment rule {rule_index}: budget_id must be string"
            )

        if not isinstance(rule["debit_sources"], list):
            raise ConfigurationError(
                f"Payment rule {rule_index}: debit_sources must be list"
            )

        if not all(isinstance(source, str) for source in rule["debit_sources"]):
            raise ConfigurationError(
                f"Payment rule {rule_index}: all debit_sources must be strings"
            )

        if not rule["debit_sources"]:
            raise ConfigurationError(
                f"Payment rule {rule_index}: debit_sources cannot be empty"
            )

        # Validate optional strategy field
        if "strategy" in rule and rule["strategy"] is not None:
            if not isinstance(rule["strategy"], str):
                raise ConfigurationError(
                    f"Payment rule {rule_index}: strategy must be string or null"
                )

        # Validate optional strategy_config field
        if "strategy_config" in rule and rule["strategy_config"] is not None:
            if not isinstance(rule["strategy_config"], dict):
                raise ConfigurationError(
                    f"Payment rule {rule_index}: strategy_config must be dictionary or null"
                )


def create_payment_config_loader(config_path: str | None = None) -> PaymentConfigLoader:
    """
    Create payment configuration loader with path from environment or parameter.

    Args:
        config_path: Optional path to configuration file. If None, uses PAYMENT_RULES_FILE env var

    Returns:
        PaymentConfigLoader: Configuration loader instance

    Raises:
        ConfigurationError: If no configuration path is available
    """
    if config_path is None:
        config_path = os.getenv("PAYMENT_RULES_FILE")

    if not config_path:
        raise ConfigurationError(
            "No payment configuration path provided. Set PAYMENT_RULES_FILE environment variable "
            "or pass config_path parameter."
        )

    return JsonPaymentConfigLoader(config_path)


def load_payment_config(config_path: str | None = None) -> PaymentConfig:
    """
    Convenience function to load payment configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        PaymentConfig: Loaded configuration

    Raises:
        ConfigurationError: If configuration cannot be loaded or is invalid
    """
    loader = create_payment_config_loader(config_path)
    return loader.load_config()


def quantize_currency(amount: Decimal) -> Decimal:
    """
    Quantize Decimal to two decimal places for currency precision.

    Args:
        amount: Decimal amount to quantize

    Returns:
        Decimal: Amount quantized to two decimal places using banker's rounding
    """
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_currency(value: str | float | int) -> Decimal:
    """
    Parse various numeric types into properly quantized Decimal currency.

    Args:
        value: Numeric value to convert to currency Decimal

    Returns:
        Decimal: Properly quantized currency amount
    """
    if isinstance(value, str):
        decimal_value = Decimal(value)
    else:
        decimal_value = Decimal(str(value))

    return quantize_currency(decimal_value)
