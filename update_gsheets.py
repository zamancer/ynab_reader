import argparse
import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.gsheets.ledger import datetime_to_gs_serial, get_worksheet, load_sheet_data
from src.gsheets.retry import retry_on_api_error
from src.ynab.reader import get_consolidated_ynab_entries
from src.ynab.ynab_types import YNABEntry

load_dotenv()

logger = logging.getLogger(__name__)

# --- SETUP INSTRUCTIONS ---
# 1. Install dependencies: pip install gspread google-auth python-dotenv
# 2. Create a Google Cloud project, enable Google Sheets API, and create a service account key (JSON file).
# 3. Share your Google Sheet with the service account email (from the JSON file) as Editor.
# 4. Place the JSON key file in your secrets folder and set its path in your .env file.
# 5. Set GSHEETS_SPREADSHEET_ID in your .env file to your target Google Sheet's ID (from its URL).


def parse_args():
    parser = argparse.ArgumentParser(description="Update Google Sheets balances.")
    parser.add_argument(
        "--testing", action="store_true", help="Use the Test worksheet if set."
    )
    return parser.parse_args()


@retry_on_api_error()
def update_ynab_balances(sheet_data, updates: list[YNABEntry], worksheet) -> list[str]:
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
            if isinstance(balance, Decimal):
                ynab_cell.value = float(balance)
            elif isinstance(balance, float) and balance.is_integer():
                ynab_cell.value = int(balance)
            else:
                ynab_cell.value = balance
            cell_updates.append(ynab_cell)
            # Update 'Ultima Actualizacion' cell as serial number
            update_cell = worksheet.cell(row_num, ultima_actualizacion_idx)
            update_cell.value = now_serial
            cell_updates.append(update_cell)
            if cuenta:
                updated_names.append(cuenta)
    if cell_updates:
        worksheet.update_cells(cell_updates)
    return updated_names


def main():
    args = parse_args()
    worksheet = get_worksheet(testing_flag=args.testing)
    data = load_sheet_data(worksheet)

    updates = get_consolidated_ynab_entries()
    if updates:
        updated_names = update_ynab_balances(data, updates, worksheet)
        logger.info(f"Updated {len(updated_names)} YNAB balances.")
        print(f"Updated {len(updated_names)} YNAB balances.")
        all_update_names = {entry["name"] for entry in updates}
        updated_names_set = set(updated_names)
        not_updated = all_update_names - updated_names_set
        if not_updated:
            logger.warning(
                f"The following YNAB balances could not be updated in the sheet: {sorted(not_updated)}"
            )
            print("The following YNAB balances could not be updated in the sheet:")
            for name in sorted(not_updated):
                print(f"- {name}")
    else:
        logger.info("No consolidated YNAB balances available.")
        print("No consolidated YNAB balances available.")


if __name__ == "__main__":
    main()
