"""
Payment summary generator workflow.

Orchestrates the complete payment summary generation process from reading account data
through generating payment instructions and writing to Google Sheets.
Follows Single Responsibility Principle - handles payment workflow orchestration only.
"""

import logging
import os
from datetime import datetime
from typing import Protocol

from src.gsheets.ledger import (
    get_credit_cards_with_debt,
    get_debit_sources_with_funds,
    load_accounts_for_payment,
)
from src.gsheets.payment_ledger import PaymentLedgerWriter
from src.payment.calculator import PaymentCalculator
from src.payment.config import JsonPaymentConfigLoader
from src.resend.email_sender import send_payment_summary_email
from src.ynab.ynab_types import PaymentInstruction, YNABAccount

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    """Protocol for email sending dependency injection."""

    def send_payment_summary_email(
        self, recipients: list[str], context: dict, testing: bool = False
    ) -> None:
        """Send payment summary email."""
        ...


class PaymentGeneratorError(Exception):
    """Raised when payment generation workflow fails."""

    pass


class PaymentGenerator:
    """
    Orchestrates the complete payment summary generation workflow.

    Coordinates account data loading, payment calculation, worksheet creation,
    and notification sending. Uses dependency injection for all external services.
    """

    def __init__(
        self,
        spreadsheet_id: str,
        config_file_path: str,
        email_sender: EmailSender | None = None,
        logger_instance: logging.Logger | None = None,
    ):
        """
        Initialize payment generator.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            config_file_path: Path to payment rules JSON configuration
            email_sender: Optional email sender for dependency injection
            logger_instance: Optional logger for dependency injection
        """
        self.spreadsheet_id = spreadsheet_id
        self.config_file_path = config_file_path
        self.email_sender = email_sender
        self.logger = logger_instance or logger

        # Initialize components
        self.config_loader = JsonPaymentConfigLoader(config_file_path)
        self.calculator = PaymentCalculator(self.config_loader)
        self.ledger_writer = PaymentLedgerWriter(spreadsheet_id)

    def generate_payment_summary(
        self,
        recipients: list[str] | None = None,
        testing: bool = False,
        dry_run: bool = False,
    ) -> list[PaymentInstruction]:
        """
        Generate complete payment summary workflow.

        Args:
            recipients: Email addresses to notify (optional)
            testing: Use test worksheet instead of production
            dry_run: Skip writing to sheets and sending emails

        Returns:
            List of generated payment instructions

        Raises:
            PaymentGeneratorError: If any step of the workflow fails
        """
        try:
            self.logger.info("Starting payment summary generation workflow")

            # Step 1: Load account data from Google Sheets
            self.logger.info("Loading account data from Cuentas worksheet")
            all_accounts = self._load_account_data(testing)
            self.logger.info(f"Loaded {len(all_accounts)} accounts from worksheet")

            # Step 2: Identify credit cards with debt and available payment sources
            credit_cards_with_debt = get_credit_cards_with_debt(all_accounts)
            if not credit_cards_with_debt:
                self.logger.info("No credit cards with debt found")
                if not dry_run and recipients:
                    self._send_no_payments_notification(recipients, testing)
                return []

            available_funds = get_debit_sources_with_funds(all_accounts)
            self.logger.info(
                f"Found {len(credit_cards_with_debt)} credit cards with debt, "
                f"{len(available_funds)} accounts with available funds"
            )

            # Step 3: Calculate payment instructions using priority strategy
            self.logger.info("Calculating payment instructions")
            payment_instructions = self.calculator.calculate_payments(
                credit_cards_with_debt, available_funds
            )

            if not payment_instructions:
                self.logger.warning("No payment instructions generated")
                if not dry_run and recipients:
                    self._send_no_payments_notification(recipients, testing)
                return []

            self.logger.info(
                f"Generated {len(payment_instructions)} payment instructions"
            )

            # Step 4: Write payment summary to Google Sheets
            if not dry_run:
                self.logger.info("Writing payment summary to Google Sheets")
                self._write_payment_summary(payment_instructions)
            else:
                self.logger.info("DRY RUN: Skipping Google Sheets write")

            # Step 5: Send notification email
            if not dry_run and recipients:
                self.logger.info(
                    f"Sending notification email to {len(recipients)} recipients"
                )
                self._send_payment_notification(
                    payment_instructions, recipients, testing
                )
            elif dry_run:
                self.logger.info("DRY RUN: Skipping email notification")

            self.logger.info("Payment summary generation completed successfully")
            return payment_instructions

        except Exception as e:
            self.logger.error(f"Payment summary generation failed: {e}")
            raise PaymentGeneratorError(
                f"Payment summary generation failed: {e}"
            ) from e

    def _load_account_data(self, testing: bool) -> list[YNABAccount]:
        """Load and validate account data from Google Sheets."""
        try:
            accounts = load_accounts_for_payment(testing)
            if not accounts:
                raise PaymentGeneratorError("No account data found in worksheet")

            # Validate that we have both credit cards and funding sources
            credit_cards = [
                acc for acc in accounts if acc["account_type"] == "credit_card"
            ]
            funding_sources = [
                acc
                for acc in accounts
                if acc["account_type"] in ("checking", "savings") and acc["balance"] > 0
            ]

            self.logger.info(
                f"Account data validation: {len(credit_cards)} credit cards, "
                f"{len(funding_sources)} funding sources"
            )

            return accounts

        except Exception as e:
            raise PaymentGeneratorError(f"Failed to load account data: {e}") from e

    def _write_payment_summary(self, instructions: list[PaymentInstruction]) -> None:
        """Write payment instructions to Google Sheets."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet = self.ledger_writer.get_or_create_payment_worksheet()
            self.ledger_writer.write_payment_instructions(
                worksheet, instructions, timestamp
            )

        except Exception as e:
            raise PaymentGeneratorError(f"Failed to write payment summary: {e}") from e

    def _send_payment_notification(
        self,
        instructions: list[PaymentInstruction],
        recipients: list[str],
        testing: bool,
    ) -> None:
        """Send payment summary notification email."""
        try:
            # Calculate summary statistics
            total_debt = sum(abs(inst["amount_due"]) for inst in instructions)
            total_payments = sum(inst["payment_amount"] for inst in instructions)
            unique_cards = len({inst["credit_card"] for inst in instructions})
            partial_payments = sum(
                1 for inst in instructions if inst["remaining_balance"] > 0
            )

            context = {
                "instructions": instructions,
                "total_debt": float(total_debt),
                "total_payments": float(total_payments),
                "unique_cards": unique_cards,
                "partial_payments": partial_payments,
                "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            if self.email_sender:
                self.email_sender.send_payment_summary_email(
                    recipients, context, testing
                )
            else:
                # Use default email sender if none injected
                send_payment_summary_email(recipients, context, testing)

        except Exception as e:
            self.logger.error(f"Failed to send payment notification: {e}")
            # Don't raise here - email failure shouldn't break the entire workflow
            # The payment summary was already written to sheets successfully

    def _send_no_payments_notification(
        self, recipients: list[str], testing: bool
    ) -> None:
        """Send notification when no payments are needed."""
        try:
            context = {
                "instructions": [],
                "total_debt": 0.0,
                "total_payments": 0.0,
                "unique_cards": 0,
                "partial_payments": 0,
                "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "no_payments_needed": True,
            }

            if self.email_sender:
                self.email_sender.send_payment_summary_email(
                    recipients, context, testing
                )
            else:
                send_payment_summary_email(recipients, context, testing)

        except Exception as e:
            self.logger.warning(f"Failed to send no-payments notification: {e}")
            # Non-critical error, continue execution


def main():
    """
    Main entry point for payment summary generation.

    Reads configuration from environment variables and executes the complete workflow.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Load configuration from environment
        spreadsheet_id = os.getenv("GSHEETS_SPREADSHEET_ID")
        config_file_path = os.getenv("PAYMENT_RULES_FILE", "payment_rules.json")
        recipients_env = os.getenv("EMAIL_RECIPIENTS", "")
        testing = os.getenv("TESTING", "false").lower() == "true"
        dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

        if not spreadsheet_id:
            raise PaymentGeneratorError(
                "GSHEETS_SPREADSHEET_ID environment variable is required"
            )

        if not os.path.exists(config_file_path):
            raise PaymentGeneratorError(
                f"Payment rules file not found: {config_file_path}"
            )

        recipients = [
            email.strip() for email in recipients_env.split(",") if email.strip()
        ]

        logger.info(f"Configuration loaded: spreadsheet_id={spreadsheet_id}")
        logger.info(f"Recipients: {len(recipients)} email addresses")
        logger.info(f"Testing mode: {testing}")
        logger.info(f"Dry run mode: {dry_run}")

        # Create and run payment generator
        generator = PaymentGenerator(spreadsheet_id, config_file_path)
        instructions = generator.generate_payment_summary(recipients, testing, dry_run)

        if instructions:
            print(f"✅ Payment summary generated with {len(instructions)} instructions")
        else:
            print("ℹ️ No payment instructions needed at this time")

    except Exception as e:
        logger.error(f"Payment generation failed: {e}")
        print(f"❌ Payment generation failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
