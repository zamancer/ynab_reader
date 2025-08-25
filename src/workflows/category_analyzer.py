from datetime import datetime, timedelta

from src.ynab.reader import (
    MAIN_BUDGET_ID,
    SECONDARY_BUDGET_ID,
    get_category_id_by_name,
    get_transactions_for_category,
)


def get_last_month_range() -> tuple[str, str]:
    """Calculate date range for last month."""
    today = datetime.now()
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_day_last_month.replace(day=1)

    start_date = first_day_last_month.strftime("%Y-%m-%d")
    end_date = last_day_last_month.strftime("%Y-%m-%d")
    return start_date, end_date


def get_current_month_range() -> tuple[str, str]:
    """Calculate date range for current month."""
    today = datetime.now()
    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    return start_date, end_date


def get_ytd_range() -> tuple[str, str]:
    """Calculate date range for year to date."""
    today = datetime.now()
    start_date = today.replace(month=1, day=1).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    return start_date, end_date


def calculate_date_range(period: str) -> tuple[str, str]:
    """Resolve period string to appropriate date range function."""
    period_functions = {
        "last_month": get_last_month_range,
        "current_month": get_current_month_range,
        "ytd": get_ytd_range,
    }

    if period not in period_functions:
        raise ValueError(f"Unsupported period: {period}")

    return period_functions[period]()


def resolve_budget_id(budget_name: str) -> str:
    """Resolve budget name to budget ID."""
    if budget_name.lower() == "main":
        if not MAIN_BUDGET_ID:
            raise ValueError("MAIN_BUDGET_ID not configured")
        return MAIN_BUDGET_ID
    elif budget_name.lower() == "secondary":
        if not SECONDARY_BUDGET_ID:
            raise ValueError("SECONDARY_BUDGET_ID not configured")
        return SECONDARY_BUDGET_ID
    else:
        raise ValueError(f"Unknown budget name: {budget_name}")


def analyze_category_spending(
    budget_name: str, category_name: str, period: str
) -> float:
    """
    Main function that orchestrates the category spending analysis.

    Returns the total amount spent in the category for the given period.
    """
    # Resolve budget ID
    budget_id = resolve_budget_id(budget_name)

    # Get category ID
    category_id = get_category_id_by_name(budget_id, category_name)
    if not category_id:
        raise ValueError(
            f"Category '{category_name}' not found in budget '{budget_name}'"
        )

    # Calculate date range
    start_date, end_date = calculate_date_range(period)

    # Fetch transactions
    transactions = get_transactions_for_category(
        budget_id, category_id, start_date, end_date
    )

    # Sum amounts (YNAB amounts are in milliunits, so divide by 1000)
    total_amount = sum(transaction["amount"] for transaction in transactions) / 1000

    return abs(total_amount)  # Return absolute value for spending
