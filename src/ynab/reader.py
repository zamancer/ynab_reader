import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from src.ynab.types import YNABEntry

load_dotenv()

YNAB_ACCESS_TOKEN = os.getenv("YNAB_ACCESS_TOKEN")
MAIN_BUDGET_ID = os.getenv("MAIN_BUDGET_ID")
SECONDARY_BUDGET_ID = os.getenv("SECONDARY_BUDGET_ID")

BASE_URL = "https://api.youneedabudget.com/v1"

headers = {"Authorization": f"Bearer {YNAB_ACCESS_TOKEN}"}


def get_accounts(budget_id: str) -> Optional[List[Dict[str, Any]]]:
    url = f"{BASE_URL}/budgets/{budget_id}/accounts"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]["accounts"]
    else:
        return None


def consolidate_credit_card_balances(
    consolidated: dict[str, YNABEntry], account: dict
) -> None:
    name = account["name"]
    balance = account["balance"]
    if not account["closed"]:
        if name in consolidated:
            consolidated[name]["balance"] += balance / 1000
            consolidated[name]["consolidated"] = True
        else:
            consolidated[name] = YNABEntry(
                name=name,
                balance=balance / 1000,
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


def get_consolidated_balances() -> Optional[dict[str, YNABEntry]]:
    main_accounts = get_accounts(MAIN_BUDGET_ID)
    secondary_accounts = get_accounts(SECONDARY_BUDGET_ID)
    if main_accounts and secondary_accounts:
        return consolidate_balances(main_accounts, secondary_accounts)
    else:
        return None


def get_consolidated_ynab_entries() -> list[YNABEntry]:
    consolidated = get_consolidated_balances()
    if not consolidated:
        return []
    return list(consolidated.values())
