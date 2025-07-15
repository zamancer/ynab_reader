import argparse
import os
from src.workflows.balance_checker import check_balance_diffs


def main():
    parser = argparse.ArgumentParser(description="YNAB Alerts Workflow")
    parser.add_argument(
        "--testing", action="store_true", help="Use the Test worksheet if set."
    )
    args = parser.parse_args()

    threshold_str = os.getenv("YNAB_ALERT_THRESHOLD_PERCENT")
    recipients_str = os.getenv("YNAB_ALERT_RECIPIENTS")

    if not threshold_str or not recipients_str:
        print(
            "Error: YNAB_ALERT_THRESHOLD_PERCENT and YNAB_ALERT_RECIPIENTS env vars must be set."
        )
        return

    try:
        threshold_percent = float(threshold_str) / 100.0
    except ValueError:
        print("Error: YNAB_ALERT_THRESHOLD_PERCENT must be a number (e.g. 20 for 20%).")
        return

    recipients = [email.strip() for email in recipients_str.split(",") if email.strip()]
    if not recipients:
        print("Error: YNAB_ALERT_RECIPIENTS must contain at least one email address.")
        return

    check_balance_diffs(threshold_percent, recipients, testing=args.testing)


if __name__ == "__main__":
    main()
