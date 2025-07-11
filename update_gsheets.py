import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import argparse
from src.ynab.types import YNABEntry
from typing import List
from src.ynab.reader import get_consolidated_ynab_entries
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# --- SETUP INSTRUCTIONS ---
# 1. Install dependencies: pip install gspread google-auth python-dotenv
# 2. Create a Google Cloud project, enable Google Sheets API, and create a service account key (JSON file).
# 3. Share your Google Sheet with the service account email (from the JSON file) as Editor.
# 4. Place the JSON key file in your secrets folder and set its path in your .env file.
# 5. Set GSHEETS_SPREADSHEET_ID in your .env file to your target Google Sheet's ID (from its URL).

load_dotenv()
SERVICE_ACCOUNT_FILE = os.getenv(
    "GSHEETS_SERVICE_ACCOUNT_FILE"
)  # Path to your service account key file
SPREADSHEET_ID = os.getenv("GSHEETS_SPREADSHEET_ID")  # Google Sheet ID
# https://docs.google.com/spreadsheets/d/1MLs3H1L1rFtORvtnnoc8HmOdM9jmWsW0PyjqYrfoZKM/edit?gid=239521179#gid=239521179

# Define the required scopes
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


def parse_args():
    parser = argparse.ArgumentParser(description="Update Google Sheets balances.")
    parser.add_argument(
        "--testing", action="store_true", help="Use the Test worksheet if set."
    )
    return parser.parse_args()


def get_gsheets_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_working_worksheet(sheet, testing_flag):
    worksheet_name = "Test" if testing_flag else "Cuentas"
    try:
        worksheet = sheet.worksheet(worksheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        print(f"Worksheet '{worksheet_name}' not found.")
        exit(1)


def load_sheet_data(worksheet):
    # Get all values
    all_values = worksheet.get_all_values()
    if not all_values or len(all_values) < 2:
        return []
    header = all_values[0]
    data_rows = all_values[1:]
    # Map each row to a dict using the header
    data = [dict(zip(header, row)) for row in data_rows]
    return data


def datetime_to_gs_serial(dt: datetime) -> float:
    """Convert a timezone-aware datetime to Google Sheets serial number."""
    gs_epoch = datetime(1899, 12, 30, tzinfo=ZoneInfo("America/Mexico_City"))
    delta = dt - gs_epoch
    return delta.days + delta.seconds / 86400 + delta.microseconds / 86400 / 1e6


def update_ynab_balances(sheet_data, updates: List[YNABEntry], worksheet) -> list[str]:
    """
    Updates the 'YNAB' column in the worksheet for rows where 'Cuenta' matches the 'name' in updates.
    Also updates the 'Ultima Actualizacion' column with the current Mexico City local timestamp as a Google Sheets serial number.
    Args:
        sheet_data: List of dicts representing the sheet rows.
        updates: List of YNABEntry.
        worksheet: gspread worksheet object.
    Returns:
        List of account names that were updated.
    """
    cuenta_to_row = {
        row.get("Cuenta", ""): idx + 2 for idx, row in enumerate(sheet_data)
    }
    header = worksheet.row_values(1)
    ynab_idx = header.index("YNAB") + 1  # 1-indexed
    ultima_actualizacion_idx = header.index("Ultima Actualizacion") + 1  # 1-indexed
    cell_updates = []
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    now_serial = datetime_to_gs_serial(now)
    updated_names = []
    for entry in updates:
        cuenta = entry.get("name")
        balance = entry.get("balance")
        row_num = cuenta_to_row.get(cuenta)
        if row_num:
            ynab_cell = worksheet.cell(row_num, ynab_idx)
            if isinstance(balance, float) and balance.is_integer():
                ynab_cell.value = int(balance)
            else:
                ynab_cell.value = balance
            cell_updates.append(ynab_cell)
            # Update 'Ultima Actualizacion' cell as serial number
            update_cell = worksheet.cell(row_num, ultima_actualizacion_idx)
            update_cell.value = now_serial
            cell_updates.append(update_cell)
            updated_names.append(cuenta)
    if cell_updates:
        worksheet.update_cells(cell_updates)
    return updated_names


def main():
    args = parse_args()
    client = get_gsheets_client()
    sheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = get_working_worksheet(sheet, args.testing)
    data = load_sheet_data(worksheet)

    updates = get_consolidated_ynab_entries()
    if updates:
        updated_names = update_ynab_balances(data, updates, worksheet)
        print(f"Updated {len(updated_names)} YNAB balances.")
        all_update_names = {entry["name"] for entry in updates}
        updated_names_set = set(updated_names)
        not_updated = all_update_names - updated_names_set
        if not_updated:
            print("The following YNAB balances could not be updated in the sheet:")
            for name in sorted(not_updated):
                print(f"- {name}")
    else:
        print("No consolidated YNAB balances available.")


if __name__ == "__main__":
    main()
