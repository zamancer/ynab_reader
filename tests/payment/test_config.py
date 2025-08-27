"""
Tests for payment configuration management.
"""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest

from src.payment.config import (
    ConfigurationError,
    JsonPaymentConfigLoader,
    create_payment_config_loader,
    load_payment_config,
)


class TestJsonPaymentConfigLoader:
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.valid_config = {
            "default_payment_sources": {
                "main": ["Main Checking", "Main Savings"],
                "secondary": ["Investment Checking", "CETES Account"],
            },
            "payment_rules": [
                {
                    "credit_card_name": "Chase Sapphire",
                    "budget_id": "main",
                    "debit_sources": ["Main Checking", "Emergency Savings"],
                },
                {
                    "credit_card_name": "Investment Card",
                    "budget_id": "secondary",
                    "debit_sources": ["Investment Checking"],
                    "strategy": "priority_ordered",
                    "strategy_config": {"min_balance": 500},
                },
            ],
            "global_strategy_defaults": {"priority_ordered": {"min_balance": 200}},
        }

    def test_load_config_success_case(self):
        """Test successful configuration loading with valid JSON."""
        # Arrange
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(self.valid_config, temp_file)
            temp_path = temp_file.name

        try:
            loader = JsonPaymentConfigLoader(temp_path)

            # Act
            result = loader.load_config()

            # Assert
            assert isinstance(result, dict)
            assert (
                result["default_payment_sources"]
                == self.valid_config["default_payment_sources"]
            )
            assert result["payment_rules"] == self.valid_config["payment_rules"]
            assert (
                result["global_strategy_defaults"]
                == self.valid_config["global_strategy_defaults"]
            )
        finally:
            os.unlink(temp_path)

    def test_load_config_file_not_found(self):
        """Test error handling when configuration file doesn't exist."""
        # Arrange
        loader = JsonPaymentConfigLoader("/nonexistent/path.json")

        # Act & Assert
        with pytest.raises(
            ConfigurationError, match="Configuration file not found or is not a file"
        ):
            loader.load_config()

    def test_load_config_path_is_directory(self):
        """Test error handling when configuration path is a directory."""
        # Arrange
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            loader = JsonPaymentConfigLoader(temp_dir)

            # Act & Assert
            with pytest.raises(
                ConfigurationError,
                match="Configuration file not found or is not a file",
            ):
                loader.load_config()

    def test_load_config_invalid_json(self):
        """Test error handling with malformed JSON."""
        # Arrange
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            temp_file.write('{"invalid": json,}')
            temp_path = temp_file.name

        try:
            loader = JsonPaymentConfigLoader(temp_path)

            # Act & Assert
            with pytest.raises(
                ConfigurationError, match="Invalid JSON in configuration file"
            ):
                loader.load_config()
        finally:
            os.unlink(temp_path)

    def test_load_config_os_error(self):
        """Test error handling for OS-level errors (like permission denied)."""
        # Arrange
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(
                {
                    "default_payment_sources": {"main": ["Account1"]},
                    "payment_rules": [],
                },
                temp_file,
            )
            temp_path = temp_file.name

        try:
            # Make file unreadable
            os.chmod(temp_path, 0o000)
            loader = JsonPaymentConfigLoader(temp_path)

            # Act & Assert
            with pytest.raises(
                ConfigurationError, match="Failed to load configuration"
            ):
                loader.load_config()
        finally:
            # Restore permissions and cleanup
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)

    def test_validate_config_missing_required_keys(self):
        """Test validation fails when required keys are missing."""
        # Arrange
        invalid_config = {"payment_rules": []}  # Missing default_payment_sources
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(
            ConfigurationError, match="Missing required configuration keys"
        ):
            loader._validate_config(invalid_config)

    def test_validate_config_invalid_default_sources_type(self):
        """Test validation fails when default_payment_sources is not a dict."""
        # Arrange
        invalid_config = {
            "default_payment_sources": ["not", "a", "dict"],
            "payment_rules": [],
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(
            ConfigurationError, match="default_payment_sources must be a dictionary"
        ):
            loader._validate_config(invalid_config)

    def test_validate_config_invalid_payment_rules_type(self):
        """Test validation fails when payment_rules is not a list."""
        # Arrange
        invalid_config = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": "not a list",
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="payment_rules must be a list"):
            loader._validate_config(invalid_config)

    def test_validate_payment_rule_missing_fields(self):
        """Test validation fails when payment rule is missing required fields."""
        # Arrange
        invalid_rule = {
            "credit_card_name": "Test Card"
        }  # Missing budget_id and debit_sources
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="missing required fields"):
            loader._validate_payment_rule(invalid_rule, 0)

    def test_validate_payment_rule_invalid_types(self):
        """Test validation fails when payment rule fields have wrong types."""
        # Arrange
        invalid_rule = {
            "credit_card_name": 123,  # Should be string
            "budget_id": "main",
            "debit_sources": ["Account1"],
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="credit_card_name must be string"):
            loader._validate_payment_rule(invalid_rule, 0)

    def test_validate_payment_rule_empty_debit_sources(self):
        """Test validation fails when debit_sources is empty."""
        # Arrange
        invalid_rule = {
            "credit_card_name": "Test Card",
            "budget_id": "main",
            "debit_sources": [],
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="debit_sources cannot be empty"):
            loader._validate_payment_rule(invalid_rule, 0)

    def test_validate_payment_rule_optional_fields(self):
        """Test validation accepts optional strategy and strategy_config fields."""
        # Arrange
        valid_rule = {
            "credit_card_name": "Test Card",
            "budget_id": "main",
            "debit_sources": ["Account1"],
            "strategy": "custom_strategy",
            "strategy_config": {"param": "value"},
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert (should not raise)
        loader._validate_payment_rule(valid_rule, 0)

    def test_validate_payment_rule_invalid_strategy_type(self):
        """Test validation fails when strategy field has wrong type."""
        # Arrange
        invalid_rule = {
            "credit_card_name": "Test Card",
            "budget_id": "main",
            "debit_sources": ["Account1"],
            "strategy": 123,  # Should be string or null
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(ConfigurationError, match="strategy must be string or null"):
            loader._validate_payment_rule(invalid_rule, 0)

    def test_validate_config_optional_global_defaults(self):
        """Test validation accepts optional global_strategy_defaults."""
        # Arrange
        config_with_defaults = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": [],
            "global_strategy_defaults": {"strategy1": {"param": "value"}},
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act
        result = loader._validate_config(config_with_defaults)

        # Assert
        assert (
            result["global_strategy_defaults"]
            == config_with_defaults["global_strategy_defaults"]
        )

    def test_validate_config_invalid_global_defaults_type(self):
        """Test validation fails when global_strategy_defaults has wrong type."""
        # Arrange
        invalid_config = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": [],
            "global_strategy_defaults": "not a dict",
        }
        loader = JsonPaymentConfigLoader("/dummy/path")

        # Act & Assert
        with pytest.raises(
            ConfigurationError, match="global_strategy_defaults must be a dictionary"
        ):
            loader._validate_config(invalid_config)


class TestConfigurationUtilityFunctions:
    def test_create_payment_config_loader_with_path(self):
        """Test creating config loader with explicit path."""
        # Arrange
        test_path = "/test/path.json"

        # Act
        loader = create_payment_config_loader(test_path)

        # Assert
        assert isinstance(loader, JsonPaymentConfigLoader)
        assert loader.config_path == Path(test_path)

    def test_create_payment_config_loader_with_env_var(self):
        """Test creating config loader using environment variable."""
        # Arrange
        test_path = "/env/path.json"

        # Act & Assert
        with patch.dict(os.environ, {"PAYMENT_RULES_FILE": test_path}):
            loader = create_payment_config_loader()
            assert isinstance(loader, JsonPaymentConfigLoader)
            assert loader.config_path == Path(test_path)

    def test_create_payment_config_loader_no_path_available(self):
        """Test error when no configuration path is available."""
        # Act & Assert
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ConfigurationError, match="No payment configuration path provided"
            ):
                create_payment_config_loader()

    def test_load_payment_config_convenience_function(self):
        """Test convenience function loads configuration correctly."""
        # Arrange
        valid_config = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": [],
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(valid_config, temp_file)
            temp_path = temp_file.name

        try:
            # Act
            result = load_payment_config(temp_path)

            # Assert
            assert (
                result["default_payment_sources"]
                == valid_config["default_payment_sources"]
            )
            assert result["payment_rules"] == valid_config["payment_rules"]
        finally:
            os.unlink(temp_path)

    def test_load_payment_config_with_env_var(self):
        """Test convenience function uses environment variable."""
        # Arrange
        valid_config = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": [],
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(valid_config, temp_file)
            temp_path = temp_file.name

        try:
            # Act & Assert
            with patch.dict(os.environ, {"PAYMENT_RULES_FILE": temp_path}):
                result = load_payment_config()
                assert (
                    result["default_payment_sources"]
                    == valid_config["default_payment_sources"]
                )
        finally:
            os.unlink(temp_path)


class TestConfigurationEdgeCases:
    def test_config_with_unicode_characters(self):
        """Test configuration handles unicode characters in strings."""
        # Arrange
        config_with_unicode = {
            "default_payment_sources": {"main": ["Cuenta Corriente", "Tarjeta débito"]},
            "payment_rules": [
                {
                    "credit_card_name": "Tarjeta Crédit México",
                    "budget_id": "main",
                    "debit_sources": ["Cuenta Corriente"],
                }
            ],
        }

        with NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as temp_file:
            json.dump(config_with_unicode, temp_file, ensure_ascii=False)
            temp_path = temp_file.name

        try:
            loader = JsonPaymentConfigLoader(temp_path)

            # Act
            result = loader.load_config()

            # Assert
            assert "Tarjeta Crédit México" in [
                rule["credit_card_name"] for rule in result["payment_rules"]
            ]
            assert "Cuenta Corriente" in result["default_payment_sources"]["main"]
        finally:
            os.unlink(temp_path)

    def test_config_with_minimal_valid_structure(self):
        """Test configuration with only required fields."""
        # Arrange
        minimal_config = {
            "default_payment_sources": {"main": ["Account1"]},
            "payment_rules": [],
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(minimal_config, temp_file)
            temp_path = temp_file.name

        try:
            loader = JsonPaymentConfigLoader(temp_path)

            # Act
            result = loader.load_config()

            # Assert
            assert (
                result["default_payment_sources"]
                == minimal_config["default_payment_sources"]
            )
            assert result["payment_rules"] == []
            assert result.get("global_strategy_defaults") is None
        finally:
            os.unlink(temp_path)
