"""
Google Sheets API retry utility.

Follows Single Responsibility Principle - handles retry logic for transient API errors.
Provides decorator for automatic retry with exponential backoff on retryable errors.
"""

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

import gspread

logger = logging.getLogger(__name__)

# Type variable for generic function return type
T = TypeVar("T")

# HTTP status codes that indicate transient errors worth retrying
RETRYABLE_STATUS_CODES = {
    429,  # Too Many Requests (rate limiting)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay in seconds between retries (default: 60.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)
    """

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.

    Args:
        error: Exception to check

    Returns:
        True if the error is a transient API error that should be retried,
        False otherwise
    """
    if not isinstance(error, gspread.exceptions.APIError):
        return False

    try:
        # Extract status code from APIError
        # APIError stores response in error.response which has a status_code attribute
        if hasattr(error, "response") and hasattr(error.response, "status_code"):
            status_code: int = error.response.status_code
            return status_code in RETRYABLE_STATUS_CODES

        # Fallback: try to parse from error args
        if error.args and isinstance(error.args[0], dict):
            status_code_fallback = error.args[0].get("code")
            if status_code_fallback is not None:
                return status_code_fallback in RETRYABLE_STATUS_CODES

        return False
    except (AttributeError, KeyError, IndexError):
        logger.debug(f"Could not extract status code from error: {error}")
        return False


def retry_on_api_error(
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function on transient Google Sheets API errors.

    Uses exponential backoff with configurable parameters. Only retries on
    errors that are likely to be transient (503, 429, 500, 502, 504).

    Args:
        config: Retry configuration. If None, uses default RetryConfig.

    Returns:
        Decorator function that wraps the target function with retry logic.

    Example:
        @retry_on_api_error()
        def get_worksheet():
            return client.open_by_key(sheet_id)

        @retry_on_api_error(RetryConfig(max_retries=5, initial_delay=2.0))
        def update_cells(cells):
            worksheet.update_cells(cells)
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: Exception | None = None
            delay = config.initial_delay

            for attempt in range(config.max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            f"Function {func.__name__} succeeded after {attempt} retries"
                        )
                    return result

                except Exception as e:
                    last_error = e

                    # Check if this is the last attempt
                    if attempt >= config.max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {config.max_retries} retries: {e}"
                        )
                        raise

                    # Check if error is retryable
                    if not is_retryable_error(e):
                        logger.info(
                            f"Function {func.__name__} failed with non-retryable error: {e}"
                        )
                        raise

                    # Log retry attempt
                    logger.warning(
                        f"Function {func.__name__} failed with retryable error: {e}. "
                        f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{config.max_retries})"
                    )

                    # Wait before retry
                    time.sleep(delay)

                    # Calculate next delay with exponential backoff, capped at max_delay
                    delay = min(delay * config.exponential_base, config.max_delay)

            # This should never be reached, but adding for type safety
            if last_error:
                raise last_error
            raise RuntimeError(f"Function {func.__name__} failed with unknown error")

        return cast(Callable[..., T], wrapper)

    return decorator
