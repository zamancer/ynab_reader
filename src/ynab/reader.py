import os
from decimal import Decimal
from typing import Any, cast

import requests
from dotenv import load_dotenv

from src.payment.config import quantize_currency
from src.ynab.ynab_types import YNABEntry

load_dotenv()

YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")
MAIN_BUDGET_ID = os.getenv("MAIN_BUDGET_ID")
SECONDARY_BUDGET_ID = os.getenv("SECONDARY_BUDGET_ID")

BASE_URL = "https://api.youneedabudget.com/v1"

headers = {"Authorization": f"Bearer {YNAB_ACCESS_TOKEN}"}


def get_accounts(budget_id: str) -> list[dict[str, Any]] | None:
    url = f"{BASE_URL}/budgets/{budget_id}/accounts"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return cast(list[dict[str, Any]], response.json()["data"]["accounts"])
    else:
        return None


def consolidate_credit_card_balances(
    consolidated: dict[str, YNABEntry], account: dict
) -> None:
    name = account["name"]
    balance = account["balance"]
    if not account["closed"]:
        if name in consolidated:
            consolidated[name]["balance"] += quantize_currency(
                Decimal(balance) / Decimal("1000")
            )
            consolidated[name]["consolidated"] = True
        else:
            consolidated[name] = YNABEntry(
                name=name,
                balance=quantize_currency(Decimal(balance) / Decimal("1000")),
                consolidated=False,
            )


def consolidate_balances(
    main_accounts: list[dict], secondary_accounts: list[dict]
) -> dict[str, YNABEntry]:
    consolidated: dict[str, YNABEntry] = {}
    for account in main_accounts:
        consolidate_credit_card_balances(consolidated, account)
    for account in secondary_accounts:
        consolidate_credit_card_balances(consolidated, account)
    return consolidated


def get_consolidated_balances() -> dict[str, YNABEntry] | None:
    if not MAIN_BUDGET_ID or not SECONDARY_BUDGET_ID:
        return None
    main_accounts = get_accounts(MAIN_BUDGET_ID)
    secondary_accounts = get_accounts(SECONDARY_BUDGET_ID)
    if main_accounts and secondary_accounts:
        return consolidate_balances(main_accounts, secondary_accounts)
    else:
        return None


def get_category_id_by_name(budget_id: str, category_name: str) -> str | None:
    """Fetches all categories for a budget and returns the ID of the matching category."""
    url = f"{BASE_URL}/budgets/{budget_id}/categories"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        categories = response.json()["data"]["category_groups"]
        for group in categories:
            for category in group["categories"]:
                if category["name"].lower() == category_name.lower():
                    return str(category["id"]) if category["id"] is not None else None
    return None


def get_transactions_for_category(
    budget_id: str, category_id: str, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    """Fetches all transactions for a given category within a date range."""
    url = f"{BASE_URL}/budgets/{budget_id}/categories/{category_id}/transactions"
    params = {"since_date": start_date}
    response = requests.get(url, headers=headers, params=params, timeout=15)
    if response.status_code == 200:
        transactions = response.json()["data"]["transactions"]
        return [t for t in transactions if t["date"] <= end_date and not t["deleted"]]
    return []


def get_consolidated_ynab_entries() -> list[YNABEntry]:
    consolidated = get_consolidated_balances()
    if not consolidated:
        return []
    return list(consolidated.values())
