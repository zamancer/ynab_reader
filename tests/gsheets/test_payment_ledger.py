from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from gspread.exceptions import WorksheetNotFound
from gspread.utils import ValueInputOption

from src.gsheets.payment_ledger import (
    PaymentLedgerError,
    PaymentLedgerWriter,
    create_payment_summary,
)
from src.ynab.ynab_types import PaymentInstruction


class TestPaymentLedgerWriter:
    """Test PaymentLedgerWriter class functionality."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.spreadsheet_id = "test_spreadsheet_id"
        self.mock_client = Mock()
        self.mock_logger = Mock()

        # Create writer with mocked dependencies
        self.writer = PaymentLedgerWriter(
            spreadsheet_id=self.spreadsheet_id,
            client=self.mock_client,
            logger_instance=self.mock_logger,
        )

        # Sample payment instructions for testing
        self.sample_instructions = [
            PaymentInstruction(
                credit_card="Chase Sapphire",
                budget_id="main",
                amount_due=Decimal("1500.00"),
                payment_source="Main Checking",
                payment_amount=Decimal("1500.00"),
                remaining_balance=Decimal("0.00"),
                payment_due_date=15,
                days_until_due=5,
                rule_type="explicit",
                strategy_used="priority_ordered",
                notes="Full payment",
            ),
            PaymentInstruction(
                credit_card="Investment Card",
                budget_id="secondary",
                amount_due=Decimal("2500.00"),
                payment_source="Investment Checking",
                payment_amount=Decimal("2000.00"),
                remaining_balance=Decimal("500.00"),
                payment_due_date=20,
                days_until_due=10,
                rule_type="default",
                strategy_used="priority_ordered",
                notes="Partial payment",
            ),
        ]

    def test_init_with_default_client(self):
        """Test initialization with default client."""
        # Arrange & Act
        with patch("src.gsheets.payment_ledger.get_gsheets_client") as mock_get_client:
            mock_get_client.return_value = Mock()
            writer = PaymentLedgerWriter("test_id")

        # Assert
        assert writer.spreadsheet_id == "test_id"
        mock_get_client.assert_called_once()

    def test_get_or_create_payment_worksheet_finds_existing(self):
        """Test finding existing payment worksheet by name."""
        # Arrange
        mock_spreadsheet = Mock()
        mock_worksheet = Mock()
        mock_worksheet.title = "Payment Summary"

        self.mock_client.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.side_effect = [
            WorksheetNotFound("Not found"),  # First name fails
            mock_worksheet,  # Second name succeeds
        ]

        # Act
        result = self.writer.get_or_create_payment_worksheet()

        # Assert
        assert result == mock_worksheet
        self.mock_client.open_by_key.assert_called_once_with(self.spreadsheet_id)
        assert mock_spreadsheet.worksheet.call_count == 2
        self.mock_logger.info.assert_called_with(
            "Found existing payment worksheet: 'Payment Summary'"
        )

    def test_get_or_create_payment_worksheet_creates_new(self):
        """Test creating new payment worksheet when none exists."""
        # Arrange
        mock_spreadsheet = Mock()
        mock_new_worksheet = Mock()

        self.mock_client.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.side_effect = WorksheetNotFound("Not found")
        mock_spreadsheet.add_worksheet.return_value = mock_new_worksheet

        # Act
        result = self.writer.get_or_create_payment_worksheet()

        # Assert
        assert result == mock_new_worksheet
        mock_spreadsheet.add_worksheet.assert_called_once_with(
            title="Payment Summary", rows=100, cols=11
        )
        self.mock_logger.info.assert_any_call("Created new 'Payment Summary' worksheet")

    def test_get_or_create_payment_worksheet_spreadsheet_error(self):
        """Test error handling when spreadsheet cannot be opened."""
        # Arrange
        self.mock_client.open_by_key.side_effect = Exception("Network error")

        # Act & Assert
        with pytest.raises(PaymentLedgerError, match="Failed to open spreadsheet"):
            self.writer.get_or_create_payment_worksheet()

    def test_setup_payment_worksheet_formatting_success(self):
        """Test successful worksheet formatting setup."""
        # Arrange
        mock_worksheet = Mock()
        mock_worksheet.id = 123456
        mock_spreadsheet = Mock()
        mock_worksheet.spreadsheet = mock_spreadsheet

        # Act
        self.writer.setup_payment_worksheet_formatting(mock_worksheet)

        # Assert
        mock_worksheet.update.assert_called_once_with(
            range_name="A1:K1",
            values=[self.writer.HEADERS],
            value_input_option=ValueInputOption.user_entered,
        )
        mock_worksheet.format.assert_called()

        # Verify batch_update was called with the correct requests
        mock_spreadsheet.batch_update.assert_called_once()
        batch_update_call = mock_spreadsheet.batch_update.call_args[0][0]
        requests = batch_update_call["requests"]

        # Verify we have all eight requests (auto-resize, validation, 3 currency formats, 2 conditional formats, freeze)
        assert len(requests) == 8

        # Verify auto-resize request
        auto_resize_request = requests[0]
        assert "autoResizeDimensions" in auto_resize_request
        assert (
            auto_resize_request["autoResizeDimensions"]["dimensions"]["sheetId"]
            == 123456
        )
        assert (
            auto_resize_request["autoResizeDimensions"]["dimensions"]["dimension"]
            == "COLUMNS"
        )
        assert (
            auto_resize_request["autoResizeDimensions"]["dimensions"]["startIndex"] == 0
        )
        assert auto_resize_request["autoResizeDimensions"]["dimensions"][
            "endIndex"
        ] == len(self.writer.HEADERS)

        # Verify data validation request
        validation_request = requests[1]
        assert "repeatCell" in validation_request
        assert validation_request["repeatCell"]["range"]["sheetId"] == 123456
        assert validation_request["repeatCell"]["range"]["startRowIndex"] == 1
        assert (
            validation_request["repeatCell"]["range"]["endRowIndex"]
            == self.writer.FORMATTING_ROW_LIMIT
        )
        assert (
            validation_request["repeatCell"]["range"]["startColumnIndex"] == 8
        )  # Column I
        assert validation_request["repeatCell"]["range"]["endColumnIndex"] == 9

        # Verify freeze request
        freeze_request = requests[7]
        assert "updateSheetProperties" in freeze_request
        assert (
            freeze_request["updateSheetProperties"]["properties"]["sheetId"] == 123456
        )
        assert (
            freeze_request["updateSheetProperties"]["properties"]["gridProperties"][
                "frozenRowCount"
            ]
            == 1
        )

        self.mock_logger.info.assert_called_with(
            "Applied formatting to Payment Summary worksheet"
        )

    def test_setup_payment_worksheet_formatting_error(self):
        """Test error handling during worksheet formatting."""
        # Arrange
        mock_worksheet = Mock()
        mock_worksheet.update.side_effect = Exception("Format error")

        # Act & Assert
        with pytest.raises(PaymentLedgerError, match="Failed to format worksheet"):
            self.writer.setup_payment_worksheet_formatting(mock_worksheet)

    def test_write_payment_instructions_success(self):
        """Test successful writing of payment instructions."""
        # Arrange
        mock_worksheet = Mock()
        timestamp = "2024-01-01 12:00:00"

        # Act
        self.writer.write_payment_instructions(
            mock_worksheet, self.sample_instructions, timestamp
        )

        # Assert
        mock_worksheet.batch_clear.assert_called_once_with(["A2:K"])
        mock_worksheet.update.assert_called()  # Called for data and summary
        self.mock_logger.info.assert_any_call("Wrote 2 payment instructions")

    def test_write_payment_instructions_empty_list(self):
        """Test writing when no payment instructions provided."""
        # Arrange
        mock_worksheet = Mock()
        timestamp = "2024-01-01 12:00:00"

        # Act
        self.writer.write_payment_instructions(mock_worksheet, [], timestamp)

        # Assert
        mock_worksheet.batch_clear.assert_called_once_with(["A2:K"])
        mock_worksheet.update.assert_called_with(
            range_name="A2",
            values=[["No hay pagos requeridos en este momento"]],
            value_input_option=ValueInputOption.user_entered,
        )
        self.mock_logger.info.assert_called_with("No payment instructions to write")

    def test_write_payment_instructions_error(self):
        """Test error handling during instruction writing."""
        # Arrange
        mock_worksheet = Mock()
        mock_worksheet.batch_clear.side_effect = Exception("Write error")
        timestamp = "2024-01-01 12:00:00"

        # Act & Assert
        with pytest.raises(
            PaymentLedgerError, match="Failed to write payment instructions"
        ):
            self.writer.write_payment_instructions(
                mock_worksheet, self.sample_instructions, timestamp
            )

    def test_prepare_data_rows_formatting(self):
        """Test conversion of payment instructions to data rows."""
        # Arrange & Act
        data_rows = self.writer._prepare_data_rows(self.sample_instructions)

        # Assert
        assert len(data_rows) == 2

        # Check first row formatting
        first_row = data_rows[0]
        assert first_row[0] == "Chase Sapphire"  # credit_card
        assert first_row[1] == "Main"  # budget_id.title()
        assert first_row[2] == -1500.0  # amount_due (raw negative number)
        assert first_row[3] == 1500.0  # payment_amount (raw number)
        assert first_row[4] == "Main Checking"  # payment_source
        assert first_row[5] == "priority_ordered"  # strategy_used
        assert first_row[6] == "explicit"  # rule_type
        assert first_row[7] == 0.0  # remaining_balance (raw number)
        assert first_row[8] == "Pendiente"  # status (default)
        assert first_row[9] == ""  # date processed (empty)
        assert first_row[10] == "Full payment"  # notes

    def test_add_summary_section_with_partial_payments(self):
        """Test summary section with partial payment alerts."""
        # Arrange
        mock_worksheet = Mock()
        timestamp = "2024-01-01 12:00:00"
        start_row = 5

        # Act
        self.writer._add_summary_section(
            mock_worksheet, self.sample_instructions, timestamp, start_row
        )

        # Assert
        mock_worksheet.update.assert_called()
        mock_worksheet.format.assert_called()
        self.mock_logger.info.assert_called_with("Added summary section to worksheet")

        # Verify the update call contains partial payment alerts
        update_call_kwargs = mock_worksheet.update.call_args[1]
        summary_data = update_call_kwargs["values"]

        # Check that partial payment info is included
        summary_text = str(summary_data)
        assert "DEUDA NO PAGADA" in summary_text
        assert "TARJETAS PARCIALES" in summary_text

    def test_add_summary_section_no_partial_payments(self):
        """Test summary section without partial payments."""
        # Arrange
        mock_worksheet = Mock()
        timestamp = "2024-01-01 12:00:00"
        start_row = 5

        # Create instructions with no remaining balance
        full_payment_instructions = [
            PaymentInstruction(
                credit_card="Test Card",
                budget_id="main",
                amount_due=Decimal("1000.00"),
                payment_source="Test Account",
                payment_amount=Decimal("1000.00"),
                remaining_balance=Decimal("0.00"),
                payment_due_date=15,
                days_until_due=5,
                rule_type="explicit",
                strategy_used="priority_ordered",
                notes="",
            )
        ]

        # Act
        self.writer._add_summary_section(
            mock_worksheet, full_payment_instructions, timestamp, start_row
        )

        # Assert
        update_call_kwargs = mock_worksheet.update.call_args[1]
        summary_data = update_call_kwargs["values"]
        summary_text = str(summary_data)

        # Partial payment alerts should not be present
        assert "DEUDA NO PAGADA" not in summary_text
        assert "TARJETAS PARCIALES" not in summary_text

    def test_add_summary_section_multiple_instructions_per_card_no_double_counting(self):
        """
        Test that summary totals aggregate per card, not per instruction.

        Regression test: When a card has multiple instructions (multiple source transfers),
        the total debt should be counted once per card, not once per instruction.
        Similarly, remaining balance should reflect the final remainder (minimum) per card.
        """
        # Arrange
        mock_worksheet = Mock()
        timestamp = "2024-01-01 12:00:00"
        start_row = 5

        # Create scenario: One card paid from two sources
        # Card has $1000 debt, paid $600 from first source, $400 from second
        instructions_with_multiple_sources = [
            PaymentInstruction(
                credit_card="Chase Sapphire",
                budget_id="main",
                amount_due=Decimal("1000.00"),  # Total debt
                payment_source="Main Checking",
                payment_amount=Decimal("600.00"),  # First transfer
                remaining_balance=Decimal("400.00"),  # After first transfer
                payment_due_date=15,
                days_until_due=5,
                rule_type="explicit",
                strategy_used="priority_ordered",
                notes="Transfer 1 of 2",
            ),
            PaymentInstruction(
                credit_card="Chase Sapphire",  # Same card
                budget_id="main",
                amount_due=Decimal("1000.00"),  # Same total debt
                payment_source="Emergency Savings",
                payment_amount=Decimal("400.00"),  # Second transfer
                remaining_balance=Decimal("0.00"),  # Final remainder after both
                payment_due_date=15,
                days_until_due=5,
                rule_type="explicit",
                strategy_used="priority_ordered",
                notes="Transfer 2 of 2",
            ),
            # Add another card to ensure aggregation works with multiple cards
            PaymentInstruction(
                credit_card="Investment Card",
                budget_id="secondary",
                amount_due=Decimal("500.00"),
                payment_source="Investment Checking",
                payment_amount=Decimal("300.00"),
                remaining_balance=Decimal("200.00"),  # Partial payment
                payment_due_date=20,
                days_until_due=10,
                rule_type="default",
                strategy_used="priority_ordered",
                notes="",
            ),
        ]

        # Act
        self.writer._add_summary_section(
            mock_worksheet, instructions_with_multiple_sources, timestamp, start_row
        )

        # Assert
        update_call_kwargs = mock_worksheet.update.call_args[1]
        summary_data = update_call_kwargs["values"]

        # Find the total debt row
        total_debt_row = None
        total_payments_row = None
        unpaid_debt_row = None

        for row in summary_data:
            if len(row) >= 2:
                if "Total Deuda:" in str(row[0]):
                    total_debt_row = row
                elif "Total Pagos:" in str(row[0]):
                    total_payments_row = row
                elif "DEUDA NO PAGADA:" in str(row[0]):
                    unpaid_debt_row = row

        # Verify total debt is NOT double-counted
        # Should be $1000 (Chase) + $500 (Investment) = $1500, NOT $2000
        assert total_debt_row is not None, "Total debt row should exist"
        assert total_debt_row[1] == 1500.0, (
            f"Total debt should be $1500 (per card aggregation), "
            f"got ${total_debt_row[1]}"
        )

        # Verify total payments sums all individual transfers
        # Should be $600 + $400 + $300 = $1300
        assert total_payments_row is not None, "Total payments row should exist"
        assert total_payments_row[1] == 1300.0, (
            f"Total payments should be $1300, got ${total_payments_row[1]}"
        )

        # Verify unpaid debt uses minimum remaining per card
        # Chase: min(400, 0) = $0, Investment: $200, Total = $200
        assert unpaid_debt_row is not None, "Unpaid debt row should exist"
        assert unpaid_debt_row[1] == 200.0, (
            f"Unpaid debt should be $200 (min remaining per card), "
            f"got ${unpaid_debt_row[1]}"
        )

        # Verify partial payment count is per card, not per instruction
        partial_count_row = None
        for row in summary_data:
            if len(row) >= 2 and "TARJETAS PARCIALES:" in str(row[0]):
                partial_count_row = row
                break

        assert partial_count_row is not None, "Partial count row should exist"
        assert "1" in str(partial_count_row[1]), (
            "Should count 1 card with partial payment, not 2 instructions"
        )


class TestCreatePaymentSummaryFunction:
    """Test the convenience function create_payment_summary."""

    @patch("src.gsheets.payment_ledger.PaymentLedgerWriter")
    def test_create_payment_summary_with_timestamp(self, mock_writer_class):
        """Test create_payment_summary with provided timestamp."""
        # Arrange
        mock_writer = Mock()
        mock_worksheet = Mock()
        mock_writer_class.return_value = mock_writer
        mock_writer.get_or_create_payment_worksheet.return_value = mock_worksheet

        spreadsheet_id = "test_id"
        instructions = []
        timestamp = "2024-01-01 10:00:00"

        # Act
        create_payment_summary(spreadsheet_id, instructions, timestamp)

        # Assert
        mock_writer_class.assert_called_once_with(spreadsheet_id)
        mock_writer.get_or_create_payment_worksheet.assert_called_once()
        mock_writer.write_payment_instructions.assert_called_once_with(
            mock_worksheet, instructions, timestamp
        )

    @patch("src.gsheets.payment_ledger.PaymentLedgerWriter")
    @patch("src.gsheets.payment_ledger.datetime")
    def test_create_payment_summary_default_timestamp(
        self, mock_datetime, mock_writer_class
    ):
        """Test create_payment_summary with default timestamp."""
        # Arrange
        mock_writer = Mock()
        mock_worksheet = Mock()
        mock_writer_class.return_value = mock_writer
        mock_writer.get_or_create_payment_worksheet.return_value = mock_worksheet

        mock_now = Mock()
        mock_now.strftime.return_value = "2024-01-01 12:00:00"
        mock_datetime.now.return_value = mock_now

        spreadsheet_id = "test_id"
        instructions = []

        # Act
        create_payment_summary(spreadsheet_id, instructions)

        # Assert
        mock_writer.write_payment_instructions.assert_called_once_with(
            mock_worksheet, instructions, "2024-01-01 12:00:00"
        )


class TestPaymentLedgerError:
    """Test PaymentLedgerError exception class."""

    def test_payment_ledger_error_inheritance(self):
        """Test that PaymentLedgerError inherits from Exception."""
        # Arrange & Act
        error = PaymentLedgerError("test error")

        # Assert
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_payment_ledger_error_with_cause(self):
        """Test PaymentLedgerError with exception chaining."""
        # Arrange
        original_error = ValueError("original error")

        # Act & Assert
        with pytest.raises(PaymentLedgerError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise PaymentLedgerError("wrapped error") from e

        assert exc_info.value.__cause__ == original_error
