import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from src.gsheets.retry import retry_on_api_error

load_dotenv()

logger = logging.getLogger(__name__)

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


@retry_on_api_error()
def get_worksheet(testing_flag: bool = False):
    """
    Get the worksheet from Google Sheets with automatic retry on transient errors.

    Args:
        testing_flag: If True, uses "Test" worksheet, otherwise "Cuentas"

    Returns:
        gspread.Worksheet object

    Raises:
        RuntimeError: If worksheet is not found
        gspread.exceptions.APIError: If API call fails after retries
    """
    client = get_gsheets_client()
    sheet = client.open_by_key(SPREADSHEET_ID)
    worksheet_name = "Test" if testing_flag else "Cuentas"
    try:
        worksheet = sheet.worksheet(worksheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        raise RuntimeError(f"Worksheet '{worksheet_name}' not found.") from None


@retry_on_api_error()
def load_sheet_data(worksheet) -> list[dict[str, Any]]:
    """
    Load all data from worksheet with automatic retry on transient errors.

    Args:
        worksheet: gspread.Worksheet object

    Returns:
        List of dictionaries, each representing a row with header keys

    Raises:
        gspread.exceptions.APIError: If API call fails after retries
    """
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
