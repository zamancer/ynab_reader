from src.gsheets.ledger import get_worksheet, load_sheet_data, parse_currency_value
from src.resend.email_sender import send_balance_alert_email


def check_balance_diffs(
    threshold_percent: float, recipients: list[str], testing: bool = False
):
    worksheet = get_worksheet(testing_flag=testing)
    data = load_sheet_data(worksheet)
    alerts = []
    for row in data:
        ynab_val = parse_currency_value(row.get("YNAB", "0"))
        if ynab_val == 0:
            continue  # Skip accounts with YNAB value 0 or empty
        diff = parse_currency_value(row.get("Diff", "0"))
        saldo = parse_currency_value(row.get("Saldo", "0"))
        if saldo == 0:
            continue  # Avoid division by zero or meaningless percentage
        percent_diff = abs(diff) / abs(saldo)
        if percent_diff > threshold_percent:
            row["PercentDiff"] = f"{percent_diff*100:.1f}%"
            alerts.append(row)
    if alerts:
        context = {"accounts": alerts, "threshold_percent": threshold_percent * 100}
        send_balance_alert_email(recipients, context)
        print(
            f"Sent alert for {len(alerts)} accounts with >{threshold_percent*100:.0f}% diff."
        )
    else:
        print("No significant percentage balance diffs found.")
