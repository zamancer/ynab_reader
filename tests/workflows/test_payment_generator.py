from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.workflows.payment_generator import (
    PaymentGenerator,
    PaymentGeneratorError,
    main,
)


class TestPaymentGenerator:
    """Test PaymentGenerator workflow orchestration."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.spreadsheet_id = "test_spreadsheet_id"
        self.config_file_path = "test_config.json"
        self.mock_email_sender = Mock()
        self.mock_logger = Mock()

        # Sample account data
        self.sample_accounts = [
            {
                "name": "Chase Sapphire",
                "balance": Decimal("-1500.00"),
                "account_type": "credit_card",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": 15,
            },
            {
                "name": "Main Checking",
                "balance": Decimal("3000.00"),
                "account_type": "checking",
                "budget_id": "main",
                "consolidated": True,
                "payment_due_date": None,
            },
            {
                "name": "Investment Card",
                "balance": Decimal("-2500.00"),
                "account_type": "credit_card",
                "budget_id": "secondary",
                "consolidated": True,
                "payment_due_date": 20,
            },
            {
                "name": "Investment Checking",
                "balance": Decimal("5000.00"),
                "account_type": "checking",
                "budget_id": "secondary",
                "consolidated": True,
                "payment_due_date": None,
            },
        ]

        # Sample payment instructions
        self.sample_instructions = [
            {
                "credit_card": "Chase Sapphire",
                "budget_id": "main",
                "amount_due": Decimal("1500.00"),
                "payment_source": "Main Checking",
                "payment_amount": Decimal("1500.00"),
                "remaining_balance": Decimal("0.00"),
                "payment_due_date": 15,
                "days_until_due": 5,
                "rule_type": "explicit",
                "strategy_used": "priority_ordered",
                "notes": "Full payment",
            }
        ]

    def test_init_creates_components(self):
        """Test that initialization creates all required components."""
        # Arrange & Act
        generator = PaymentGenerator(
            self.spreadsheet_id,
            self.config_file_path,
            self.mock_email_sender,
            self.mock_logger,
        )

        # Assert
        assert generator.spreadsheet_id == self.spreadsheet_id
        assert generator.config_file_path == self.config_file_path
        assert generator.email_sender == self.mock_email_sender
        assert generator.logger == self.mock_logger
        assert generator.config_loader is not None
        assert generator.calculator is not None
        assert generator.ledger_writer is not None

    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_load_account_data_success(self, mock_load_accounts):
        """Test successful account data loading."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_load_accounts.return_value = self.sample_accounts

        # Act
        result = generator._load_account_data(testing=True)

        # Assert
        assert result == self.sample_accounts
        mock_load_accounts.assert_called_once_with(True)

    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_load_account_data_empty(self, mock_load_accounts):
        """Test error handling when no account data found."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_load_accounts.return_value = []

        # Act & Assert
        with pytest.raises(
            PaymentGeneratorError, match="No account data found in worksheet"
        ):
            generator._load_account_data(testing=False)

    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_load_account_data_exception(self, mock_load_accounts):
        """Test error handling during account data loading."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_load_accounts.side_effect = Exception("Load error")

        # Act & Assert
        with pytest.raises(PaymentGeneratorError, match="Failed to load account data"):
            generator._load_account_data(testing=False)

    def test_write_payment_summary_success(self):
        """Test successful payment summary writing."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_worksheet = Mock()
        generator.ledger_writer = Mock()
        generator.ledger_writer.get_or_create_payment_worksheet.return_value = (
            mock_worksheet
        )

        # Act
        generator._write_payment_summary(self.sample_instructions)

        # Assert
        generator.ledger_writer.get_or_create_payment_worksheet.assert_called_once()
        generator.ledger_writer.write_payment_instructions.assert_called_once()

    def test_write_payment_summary_error(self):
        """Test error handling during payment summary writing."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        generator.ledger_writer = Mock()
        generator.ledger_writer.get_or_create_payment_worksheet.side_effect = Exception(
            "Write error"
        )

        # Act & Assert
        with pytest.raises(
            PaymentGeneratorError, match="Failed to write payment summary"
        ):
            generator._write_payment_summary(self.sample_instructions)

    def test_send_payment_notification_with_injected_sender(self):
        """Test payment notification with injected email sender."""
        # Arrange
        generator = PaymentGenerator(
            self.spreadsheet_id, self.config_file_path, self.mock_email_sender
        )
        recipients = ["test@example.com"]

        # Act
        generator._send_payment_notification(
            self.sample_instructions, recipients, testing=True
        )

        # Assert
        self.mock_email_sender.send_payment_summary_email.assert_called_once()
        call_args = self.mock_email_sender.send_payment_summary_email.call_args
        assert call_args[0][0] == recipients
        assert call_args[0][2] is True  # testing flag

    @patch("src.workflows.payment_generator.send_payment_summary_email")
    def test_send_payment_notification_with_default_sender(self, mock_send_email):
        """Test payment notification with default email sender."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        recipients = ["test@example.com"]

        # Act
        generator._send_payment_notification(
            self.sample_instructions, recipients, testing=False
        )

        # Assert
        mock_send_email.assert_called_once()

    def test_send_payment_notification_calculates_statistics(self):
        """Test that payment notification calculates correct statistics."""
        # Arrange
        generator = PaymentGenerator(
            self.spreadsheet_id, self.config_file_path, self.mock_email_sender
        )
        recipients = ["test@example.com"]

        # Create instructions with partial payments
        instructions_with_partial = [
            {
                "credit_card": "Card 1",
                "budget_id": "main",
                "amount_due": Decimal("1000.00"),
                "payment_source": "Account 1",
                "payment_amount": Decimal("1000.00"),
                "remaining_balance": Decimal("0.00"),
                "payment_due_date": 15,
                "days_until_due": 5,
                "rule_type": "explicit",
                "strategy_used": "priority_ordered",
                "notes": "",
            },
            {
                "credit_card": "Card 2",
                "budget_id": "main",
                "amount_due": Decimal("2000.00"),
                "payment_source": "Account 1",
                "payment_amount": Decimal("1500.00"),
                "remaining_balance": Decimal("500.00"),  # Partial payment
                "payment_due_date": 20,
                "days_until_due": 10,
                "rule_type": "default",
                "strategy_used": "priority_ordered",
                "notes": "",
            },
        ]

        # Act
        generator._send_payment_notification(
            instructions_with_partial, recipients, testing=False
        )

        # Assert
        call_args = self.mock_email_sender.send_payment_summary_email.call_args
        context = call_args[0][1]

        assert context["total_debt"] == 3000.0  # 1000 + 2000
        assert context["total_payments"] == 2500.0  # 1000 + 1500
        assert context["unique_cards"] == 2
        assert context["partial_payments"] == 1

    def test_send_no_payments_notification_success(self):
        """Test sending notification when no payments are needed."""
        # Arrange
        generator = PaymentGenerator(
            self.spreadsheet_id, self.config_file_path, self.mock_email_sender
        )
        recipients = ["test@example.com"]

        # Act
        generator._send_no_payments_notification(recipients, testing=True)

        # Assert
        self.mock_email_sender.send_payment_summary_email.assert_called_once()
        call_args = self.mock_email_sender.send_payment_summary_email.call_args
        context = call_args[0][1]

        assert context["no_payments_needed"] is True
        assert context["total_debt"] == 0.0
        assert context["instructions"] == []

    @patch("src.workflows.payment_generator.get_credit_cards_with_debt")
    @patch("src.workflows.payment_generator.get_debit_sources_with_funds")
    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_generate_payment_summary_no_credit_cards_with_debt(
        self, mock_load_accounts, mock_get_debit_sources, mock_get_credit_cards
    ):
        """Test workflow when no credit cards have debt."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_load_accounts.return_value = self.sample_accounts
        mock_get_credit_cards.return_value = []  # No cards with debt
        mock_get_debit_sources.return_value = [self.sample_accounts[1]]

        # Act
        result = generator.generate_payment_summary(
            recipients=["test@example.com"], dry_run=True
        )

        # Assert
        assert result == []
        mock_get_credit_cards.assert_called_once_with(self.sample_accounts)

    @patch("src.workflows.payment_generator.get_credit_cards_with_debt")
    @patch("src.workflows.payment_generator.get_debit_sources_with_funds")
    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_generate_payment_summary_no_payment_instructions(
        self, mock_load_accounts, mock_get_debit_sources, mock_get_credit_cards
    ):
        """Test workflow when calculator generates no instructions."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        generator.calculator = Mock()
        generator.calculator.calculate_payments.return_value = []

        mock_load_accounts.return_value = self.sample_accounts
        mock_get_credit_cards.return_value = [self.sample_accounts[0]]
        mock_get_debit_sources.return_value = [self.sample_accounts[1]]

        # Act
        result = generator.generate_payment_summary(
            recipients=["test@example.com"], dry_run=True
        )

        # Assert
        assert result == []

    @patch("src.workflows.payment_generator.get_credit_cards_with_debt")
    @patch("src.workflows.payment_generator.get_debit_sources_with_funds")
    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_generate_payment_summary_successful_workflow(
        self, mock_load_accounts, mock_get_debit_sources, mock_get_credit_cards
    ):
        """Test complete successful payment summary generation workflow."""
        # Arrange
        generator = PaymentGenerator(
            self.spreadsheet_id, self.config_file_path, self.mock_email_sender
        )

        # Mock all dependencies
        generator.calculator = Mock()
        generator.calculator.calculate_payments.return_value = self.sample_instructions
        generator.ledger_writer = Mock()
        mock_worksheet = Mock()
        generator.ledger_writer.get_or_create_payment_worksheet.return_value = (
            mock_worksheet
        )

        mock_load_accounts.return_value = self.sample_accounts
        mock_get_credit_cards.return_value = [
            self.sample_accounts[0],
            self.sample_accounts[2],
        ]
        mock_get_debit_sources.return_value = [
            self.sample_accounts[1],
            self.sample_accounts[3],
        ]

        # Act
        result = generator.generate_payment_summary(
            recipients=["test@example.com"], testing=True, dry_run=False
        )

        # Assert
        assert result == self.sample_instructions

        # Verify all workflow steps were called
        mock_load_accounts.assert_called_once_with(True)
        mock_get_credit_cards.assert_called_once_with(self.sample_accounts)
        mock_get_debit_sources.assert_called_once_with(self.sample_accounts)
        generator.calculator.calculate_payments.assert_called_once()
        generator.ledger_writer.get_or_create_payment_worksheet.assert_called_once()
        generator.ledger_writer.write_payment_instructions.assert_called_once()
        self.mock_email_sender.send_payment_summary_email.assert_called_once()

    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_generate_payment_summary_dry_run_mode(self, mock_load_accounts):
        """Test that dry run mode skips writing and emailing."""
        # Arrange
        generator = PaymentGenerator(
            self.spreadsheet_id, self.config_file_path, self.mock_email_sender
        )

        generator.calculator = Mock()
        generator.calculator.calculate_payments.return_value = self.sample_instructions
        generator.ledger_writer = Mock()

        mock_load_accounts.return_value = self.sample_accounts

        with patch(
            "src.workflows.payment_generator.get_credit_cards_with_debt"
        ) as mock_get_credit_cards:
            with patch(
                "src.workflows.payment_generator.get_debit_sources_with_funds"
            ) as mock_get_debit_sources:
                mock_get_credit_cards.return_value = [self.sample_accounts[0]]
                mock_get_debit_sources.return_value = [self.sample_accounts[1]]

                # Act
                result = generator.generate_payment_summary(
                    recipients=["test@example.com"], testing=False, dry_run=True
                )

        # Assert
        assert result == self.sample_instructions
        generator.ledger_writer.get_or_create_payment_worksheet.assert_not_called()
        self.mock_email_sender.send_payment_summary_email.assert_not_called()

    @patch("src.workflows.payment_generator.load_accounts_for_payment")
    def test_generate_payment_summary_workflow_exception(self, mock_load_accounts):
        """Test error handling when workflow step fails."""
        # Arrange
        generator = PaymentGenerator(self.spreadsheet_id, self.config_file_path)
        mock_load_accounts.side_effect = Exception("Unexpected error")

        # Act & Assert
        with pytest.raises(
            PaymentGeneratorError, match="Payment summary generation failed"
        ):
            generator.generate_payment_summary()


class TestMainFunction:
    """Test the main entry point function."""

    @patch.dict(
        "os.environ",
        {
            "GSHEETS_SPREADSHEET_ID": "test_spreadsheet_id",
            "PAYMENT_RULES_FILE": "test_rules.json",
            "EMAIL_RECIPIENTS": "test1@example.com,test2@example.com",
            "TESTING": "true",
            "DRY_RUN": "false",
        },
    )
    @patch("src.workflows.payment_generator.os.path.exists")
    @patch("src.workflows.payment_generator.PaymentGenerator")
    @patch("builtins.print")
    def test_main_successful_execution(
        self, mock_print, mock_generator_class, mock_path_exists
    ):
        """Test successful main function execution."""
        # Arrange
        mock_path_exists.return_value = True
        mock_generator = Mock()
        mock_generator.generate_payment_summary.return_value = [Mock()]
        mock_generator_class.return_value = mock_generator

        # Act
        main()

        # Assert
        mock_generator_class.assert_called_once_with(
            "test_spreadsheet_id", "test_rules.json"
        )
        mock_generator.generate_payment_summary.assert_called_once_with(
            ["test1@example.com", "test2@example.com"], True, False
        )
        mock_print.assert_called_with(
            "✅ Payment summary generated with 1 instructions"
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("builtins.print")
    def test_main_missing_spreadsheet_id(self, mock_print):
        """Test main function with missing spreadsheet ID."""
        # Arrange & Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with(
            "❌ Payment generation failed: GSHEETS_SPREADSHEET_ID environment variable is required"
        )

    @patch.dict("os.environ", {"GSHEETS_SPREADSHEET_ID": "test_id"})
    @patch("src.workflows.payment_generator.os.path.exists")
    @patch("builtins.print")
    def test_main_missing_config_file(self, mock_print, mock_path_exists):
        """Test main function with missing configuration file."""
        # Arrange
        mock_path_exists.return_value = False

        # Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with(
            "❌ Payment generation failed: Payment rules file not found: payment_rules.json"
        )

    @patch.dict(
        "os.environ",
        {
            "GSHEETS_SPREADSHEET_ID": "test_id",
            "EMAIL_RECIPIENTS": "test@example.com, , another@example.com,  ",
        },
    )
    @patch("src.workflows.payment_generator.os.path.exists")
    @patch("src.workflows.payment_generator.PaymentGenerator")
    def test_main_parses_recipients_correctly(
        self, mock_generator_class, mock_path_exists
    ):
        """Test that main function correctly parses email recipients."""
        # Arrange
        mock_path_exists.return_value = True
        mock_generator = Mock()
        mock_generator.generate_payment_summary.return_value = []
        mock_generator_class.return_value = mock_generator

        # Act
        main()

        # Assert
        # Should filter out empty strings and strip whitespace
        expected_recipients = ["test@example.com", "another@example.com"]
        mock_generator.generate_payment_summary.assert_called_once_with(
            expected_recipients, False, False
        )

    @patch.dict("os.environ", {"GSHEETS_SPREADSHEET_ID": "test_id"})
    @patch("src.workflows.payment_generator.os.path.exists")
    @patch("src.workflows.payment_generator.PaymentGenerator")
    @patch("builtins.print")
    def test_main_no_instructions_generated(
        self, mock_print, mock_generator_class, mock_path_exists
    ):
        """Test main function when no payment instructions are generated."""
        # Arrange
        mock_path_exists.return_value = True
        mock_generator = Mock()
        mock_generator.generate_payment_summary.return_value = []
        mock_generator_class.return_value = mock_generator

        # Act
        main()

        # Assert
        mock_print.assert_called_with("ℹ️ No payment instructions needed at this time")

    @patch.dict("os.environ", {"GSHEETS_SPREADSHEET_ID": "test_id"})
    @patch("src.workflows.payment_generator.os.path.exists")
    @patch("src.workflows.payment_generator.PaymentGenerator")
    @patch("builtins.print")
    def test_main_handles_payment_generator_error(
        self, mock_print, mock_generator_class, mock_path_exists
    ):
        """Test main function error handling."""
        # Arrange
        mock_path_exists.return_value = True
        mock_generator = Mock()
        mock_generator.generate_payment_summary.side_effect = PaymentGeneratorError(
            "Test error"
        )
        mock_generator_class.return_value = mock_generator

        # Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with("❌ Payment generation failed: Test error")
