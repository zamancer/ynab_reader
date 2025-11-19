"""
test_gsheets_retry.py

Tests for Google Sheets retry decorator following AAA pattern:
- Arrange: Set up test data and mocks
- Act: Execute the function/method being tested
- Assert: Verify expected behavior
"""
from unittest.mock import Mock, patch

import gspread
import pytest

from src.gsheets.retry import (
    RetryConfig,
    is_retryable_error,
    retry_on_api_error,
)


class TestIsRetryableError:
    """Tests for is_retryable_error function."""

    def test_retryable_503_service_unavailable(self):
        """Test that 503 errors are retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 503, "message": "The service is currently unavailable."}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is True

    def test_retryable_429_rate_limit(self):
        """Test that 429 rate limit errors are retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 429, "message": "Rate limit exceeded"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is True

    def test_retryable_500_internal_server_error(self):
        """Test that 500 internal server errors are retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 500, "message": "Internal server error"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is True

    def test_retryable_502_bad_gateway(self):
        """Test that 502 bad gateway errors are retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 502, "message": "Bad gateway"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is True

    def test_retryable_504_gateway_timeout(self):
        """Test that 504 gateway timeout errors are retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 504, "message": "Gateway timeout"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is True

    def test_non_retryable_404_not_found(self):
        """Test that 404 errors are not retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 404, "message": "Not found"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is False

    def test_non_retryable_400_bad_request(self):
        """Test that 400 errors are not retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 400, "message": "Bad request"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is False

    def test_non_retryable_403_forbidden(self):
        """Test that 403 errors are not retryable."""
        # Arrange
        error = gspread.exceptions.APIError(
            {"code": 403, "message": "Forbidden"}
        )

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is False

    def test_non_api_error_exception(self):
        """Test that non-APIError exceptions are not retryable."""
        # Arrange
        error = ValueError("Some other error")

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is False

    def test_worksheet_not_found_not_retryable(self):
        """Test that WorksheetNotFound errors are not retryable."""
        # Arrange
        error = gspread.exceptions.WorksheetNotFound("Worksheet not found")

        # Act
        result = is_retryable_error(error)

        # Assert
        assert result is False


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self):
        """Test default retry configuration values."""
        # Arrange & Act
        config = RetryConfig()

        # Assert
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0

    def test_custom_config(self):
        """Test custom retry configuration values."""
        # Arrange & Act
        config = RetryConfig(
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0
        )

        # Assert
        assert config.max_retries == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0


class TestRetryOnApiError:
    """Tests for retry_on_api_error decorator."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_func = Mock()

    def test_success_no_retry_needed(self):
        """Test successful execution with no retries."""
        # Arrange
        self.mock_func.return_value = "success"
        decorated = retry_on_api_error()(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 1

    def test_retry_on_503_then_success(self):
        """Test retry on 503 error followed by success."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        self.mock_func.side_effect = [api_error, "success"]
        config = RetryConfig(initial_delay=0.01)  # Fast retry for testing
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 2

    def test_retry_multiple_times_then_success(self):
        """Test multiple retries before success."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        self.mock_func.side_effect = [api_error, api_error, "success"]
        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 3

    def test_max_retries_exceeded(self):
        """Test that exception is raised when max retries exceeded."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        self.mock_func.side_effect = api_error
        config = RetryConfig(max_retries=2, initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act & Assert
        with pytest.raises(gspread.exceptions.APIError):
            decorated()
        assert self.mock_func.call_count == 3  # Initial + 2 retries

    def test_non_retryable_error_no_retry(self):
        """Test that non-retryable errors are not retried."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 404, "message": "Not found"}
        )
        self.mock_func.side_effect = api_error
        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act & Assert
        with pytest.raises(gspread.exceptions.APIError):
            decorated()
        assert self.mock_func.call_count == 1  # No retries

    def test_non_api_error_no_retry(self):
        """Test that non-API errors are not retried."""
        # Arrange
        self.mock_func.side_effect = ValueError("Some error")
        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act & Assert
        with pytest.raises(ValueError):
            decorated()
        assert self.mock_func.call_count == 1  # No retries

    @patch("time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        """Test that exponential backoff delays are applied correctly."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        self.mock_func.side_effect = [api_error, api_error, api_error, "success"]
        config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            exponential_base=2.0
        )
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 4
        # Verify exponential backoff: 1.0, 2.0, 4.0
        assert mock_sleep.call_count == 3
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(1.0, rel=0.1)
        assert delays[1] == pytest.approx(2.0, rel=0.1)
        assert delays[2] == pytest.approx(4.0, rel=0.1)

    @patch("time.sleep")
    def test_max_delay_cap(self, mock_sleep):
        """Test that delay is capped at max_delay."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        self.mock_func.side_effect = [api_error, api_error, "success"]
        config = RetryConfig(
            max_retries=3,
            initial_delay=50.0,
            max_delay=60.0,
            exponential_base=2.0
        )
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        # First delay: 50.0, second delay: min(100.0, 60.0) = 60.0
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(50.0, rel=0.1)
        assert delays[1] == pytest.approx(60.0, rel=0.1)  # Capped at max_delay

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves original function metadata."""
        # Arrange
        def sample_function():
            """Sample docstring."""
            return "result"

        # Act
        decorated = retry_on_api_error()(sample_function)

        # Assert
        assert decorated.__name__ == "sample_function"
        assert decorated.__doc__ == "Sample docstring."

    def test_decorator_with_args_and_kwargs(self):
        """Test that decorator works with functions that have arguments."""
        # Arrange
        def add_numbers(a: int, b: int, multiplier: int = 1) -> int:
            return (a + b) * multiplier

        api_error = gspread.exceptions.APIError(
            {"code": 503, "message": "Service unavailable"}
        )
        mock_func = Mock(side_effect=[api_error, 15])
        mock_func.__name__ = "add_numbers"
        mock_func.__doc__ = "Adds numbers"

        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(mock_func)

        # Act
        result = decorated(5, 3, multiplier=2)

        # Assert
        assert result == 15
        assert mock_func.call_count == 2
        # Verify args were passed correctly
        mock_func.assert_called_with(5, 3, multiplier=2)

    def test_retry_on_429_rate_limit(self):
        """Test retry on 429 rate limit error."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 429, "message": "Rate limit exceeded"}
        )
        self.mock_func.side_effect = [api_error, "success"]
        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 2

    def test_retry_on_500_internal_server_error(self):
        """Test retry on 500 internal server error."""
        # Arrange
        api_error = gspread.exceptions.APIError(
            {"code": 500, "message": "Internal server error"}
        )
        self.mock_func.side_effect = [api_error, "success"]
        config = RetryConfig(initial_delay=0.01)
        decorated = retry_on_api_error(config)(self.mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert self.mock_func.call_count == 2
