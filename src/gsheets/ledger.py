import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from src.ynab.ynab_types import YNABAccount

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv("GSHEETS_SERVICE_ACCOUNT_FILE")
SPREADSHEET_ID = os.getenv("GSHEETS_SPREADSHEET_ID")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_COLUMNS = [
    "ID",
    "Cuenta",
    "Saldo",
    "YNAB",
    "Diff",
    "Tipo Cuenta",
    "Fecha Corte",
    "Fecha Pago",
    "Ultima Actualizacion",
    "Cuenta YNAB",
]


def get_gsheets_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(testing_flag: bool = False):
    client = get_gsheets_client()
    sheet = client.open_by_key(SPREADSHEET_ID)
    worksheet_name = "Test" if testing_flag else "Cuentas"
    try:
        worksheet = sheet.worksheet(worksheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        raise RuntimeError(f"Worksheet '{worksheet_name}' not found.") from None


def load_sheet_data(worksheet) -> list[dict[str, Any]]:
    all_values = worksheet.get_all_values()
    if not all_values or len(all_values) < 2:
        return []
    header = all_values[0]
    data_rows = all_values[1:]
    data = [dict(zip(header, row, strict=False)) for row in data_rows]
    return data


def datetime_to_gs_serial(dt: datetime) -> float:
    gs_epoch = datetime(1899, 12, 30, tzinfo=ZoneInfo("America/Mexico_City"))
    delta = dt - gs_epoch
    return delta.days + delta.seconds / 86400 + delta.microseconds / 86400 / 1e6


def parse_currency_value(value: str) -> float:
    """Parse a currency string like "$1,234.56" or "-$123.45" or empty to float."""
    if not value or not isinstance(value, str):
        return 0.0
    cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned == "" or cleaned == "-":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_currency_to_decimal(value: str) -> Decimal:
    """Parse a currency string to Decimal for payment calculations."""
    if not value or not isinstance(value, str):
        return Decimal("0.0")
    cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned == "" or cleaned == "-":
        return Decimal("0.0")
    try:
        return Decimal(cleaned)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0.0")


def parse_payment_due_date(value: str) -> int | None:
    """Parse payment due date string to day of month (1-31) or None if invalid."""
    if not value or not isinstance(value, str):
        return None

    # Handle various date formats
    cleaned = value.strip()
    if not cleaned or cleaned == "-":
        return None

    try:
        # Try to parse as day of month (1-31)
        day = int(cleaned)
        if 1 <= day <= 31:
            return day
    except ValueError:
        pass

    # Try to parse as date and extract day
    try:
        # Handle DD/MM/YYYY or DD-MM-YYYY formats
        if "/" in cleaned or "-" in cleaned:
            separator = "/" if "/" in cleaned else "-"
            parts = cleaned.split(separator)
            if len(parts) >= 1:
                day = int(parts[0])
                if 1 <= day <= 31:
                    return day
    except (ValueError, IndexError):
        pass

    return None


def load_accounts_for_payment(testing_flag: bool = False) -> list[YNABAccount]:
    """
    Load account data from Cuentas worksheet formatted for payment calculations.

    Returns accounts with payment due dates parsed from "Fecha Pago" column.
    """
    worksheet = get_worksheet(testing_flag)
    raw_data = load_sheet_data(worksheet)

    accounts: list[YNABAccount] = []

    for row in raw_data:
        # Skip empty rows or rows without account names
        account_name = row.get("Cuenta", "").strip()
        if not account_name:
            continue

        # Parse balance using Decimal for precision
        balance_str = row.get("Saldo", "")
        balance = parse_currency_to_decimal(balance_str)

        # Determine account type from "Tipo Cuenta" column
        account_type_raw = row.get("Tipo Cuenta", "").lower().strip()
        if "credit" in account_type_raw or "tarjeta" in account_type_raw:
            account_type = "credit_card"
        elif "checking" in account_type_raw or "corriente" in account_type_raw:
            account_type = "checking"
        elif "savings" in account_type_raw or "ahorro" in account_type_raw:
            account_type = "savings"
        else:
            # Default to checking for unknown types
            account_type = "checking"

        # Parse payment due date from "Fecha Pago" column
        payment_due_date = parse_payment_due_date(row.get("Fecha Pago", ""))

        # Extract budget_id from account name or default logic
        # This could be enhanced based on naming conventions
        budget_id = "main"  # Default to main budget
        if any(
            keyword in account_name.lower()
            for keyword in ["investment", "inversión", "secondary", "secundario"]
        ):
            budget_id = "secondary"

        # Determine if account should be consolidated
        consolidated = row.get("YNAB", "").strip() != ""

        account = YNABAccount(
            name=account_name,
            balance=balance,
            account_type=account_type,
            budget_id=budget_id,
            consolidated=consolidated,
            payment_due_date=payment_due_date,
        )

        accounts.append(account)

    return accounts


def get_credit_cards_with_debt(accounts: list[YNABAccount]) -> list[YNABAccount]:
    """Filter accounts to return only credit cards with negative balances (debt)."""
    return [
        account
        for account in accounts
        if account["account_type"] == "credit_card" and account["balance"] < 0
    ]


def get_debit_sources_with_funds(
    accounts: list[YNABAccount], budget_id: str | None = None
) -> list[YNABAccount]:
    """
    Filter accounts to return checking/savings accounts with positive balances.

    Args:
        accounts: List of all accounts
        budget_id: Optional budget filter. If provided, only return accounts from that budget.

    Returns:
        List of debit accounts with positive balances
    """
    debit_accounts = [
        account
        for account in accounts
        if account["account_type"] in ("checking", "savings") and account["balance"] > 0
    ]

    if budget_id:
        debit_accounts = [
            account for account in debit_accounts if account["budget_id"] == budget_id
        ]

    return debit_accounts
