"""
Payment ledger operations for Google Sheets integration.

Handles creating and managing the "Payment Summary" worksheet with payment instructions.
Handles Google Sheets payment operations only.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import gspread
from gspread.exceptions import WorksheetNotFound

from src.gsheets.ledger import get_gsheets_client
from src.ynab.ynab_types import PaymentInstruction

logger = logging.getLogger(__name__)


class SpreadsheetClient(Protocol):
    """Protocol for Google Sheets client dependency injection."""

    def open_by_key(self, key: str) -> gspread.Spreadsheet: ...


class PaymentLedgerError(Exception):
    """Raised when payment ledger operations fail."""

    pass


class PaymentLedgerWriter:
    """
    Manages Payment Summary worksheet creation and data writing.

    Handles worksheet discovery, creation, formatting, and content management
    for payment instruction data.
    """

    PAYMENT_SHEET_NAMES = [
        "Payment Summary",
        "Resumen de Pagos",
        "Payments",
        "Pagos",
    ]

    HEADERS = [
        "Tarjeta de Crédito",
        "Presupuesto",
        "Saldo Actual",
        "Monto a Pagar",
        "Cuenta de Origen",
        "Estrategia",
        "Tipo de Regla",
        "Balance Restante",
        "Estado",
        "Fecha Procesado",
        "Notas",
    ]

    STATUS_OPTIONS = ["Pendiente", "Procesado", "Verificado", "Error"]

    def __init__(
        self,
        spreadsheet_id: str,
        client: SpreadsheetClient | None = None,
        logger_instance: logging.Logger | None = None,
    ):
        """
        Initialize payment ledger writer.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            client: Optional spreadsheet client for dependency injection
            logger_instance: Optional logger for dependency injection
        """
        self.spreadsheet_id = spreadsheet_id
        self.client = client or get_gsheets_client()
        self.logger = logger_instance or logger

    def get_or_create_payment_worksheet(self) -> gspread.Worksheet:
        """
        Smart worksheet management - find existing or create new Payment Summary sheet.

        Returns:
            Google Sheets worksheet for payment summary

        Raises:
            PaymentLedgerError: If worksheet operations fail
        """
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        except Exception as e:
            raise PaymentLedgerError(f"Failed to open spreadsheet: {e}") from e

        # Try to find existing payment worksheet
        existing_worksheet = self._find_existing_payment_worksheet(spreadsheet)
        if existing_worksheet:
            self.logger.info(
                f"Found existing payment worksheet: '{existing_worksheet.title}'"
            )
            return existing_worksheet

        # Create new worksheet if not found
        return self._create_new_payment_worksheet(spreadsheet)

    def _find_existing_payment_worksheet(
        self, spreadsheet: gspread.Spreadsheet
    ) -> gspread.Worksheet | None:
        """Search for existing payment worksheet by name."""
        for sheet_name in self.PAYMENT_SHEET_NAMES:
            try:
                return spreadsheet.worksheet(sheet_name)
            except WorksheetNotFound:
                continue
        return None

    def _create_new_payment_worksheet(
        self, spreadsheet: gspread.Spreadsheet
    ) -> gspread.Worksheet:
        """Create new payment worksheet with proper formatting."""
        try:
            new_worksheet = spreadsheet.add_worksheet(
                title="Payment Summary",
                rows=100,  # Initial size
                cols=len(self.HEADERS),
            )
            self.logger.info("Created new 'Payment Summary' worksheet")

            # Set up initial formatting and headers
            self.setup_payment_worksheet_formatting(new_worksheet)
            return new_worksheet

        except Exception as e:
            raise PaymentLedgerError(
                f"Failed to create Payment Summary worksheet: {e}"
            ) from e

    def setup_payment_worksheet_formatting(self, worksheet: gspread.Worksheet) -> None:
        """
        Initialize worksheet with headers, formatting, and validation.

        Args:
            worksheet: Google Sheets worksheet to format

        Raises:
            PaymentLedgerError: If formatting operations fail
        """
        try:
            # Set headers in row 1
            worksheet.update("A1:K1", [self.HEADERS])  # type: ignore[arg-type]

            # Apply header formatting
            worksheet.format(
                "A1:K1",
                {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                    "horizontalAlignment": "CENTER",
                },
            )

            # Apply column auto-resize, data validation, and freeze header using batch_update
            sheet_id = worksheet.id
            requests = [
                # Auto-resize all columns
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": len(self.HEADERS),
                        }
                    }
                },
                # Add data validation for Status column (I) rows 2-100
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Row 2 (0-indexed)
                            "endRowIndex": 100,  # Row 100 (exclusive)
                            "startColumnIndex": 8,  # Column I (0-indexed)
                            "endColumnIndex": 9,  # Column I (exclusive)
                        },
                        "cell": {
                            "dataValidation": {
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": [
                                        {"userEnteredValue": option}
                                        for option in self.STATUS_OPTIONS
                                    ],
                                },
                                "showCustomUi": True,
                            }
                        },
                        "fields": "dataValidation",
                    }
                },
                # Apply currency formatting to amount columns (C, D, H)
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Row 2 onwards (0-indexed)
                            "endRowIndex": 1000,  # Large range for future data
                            "startColumnIndex": 2,  # Column C (Saldo Actual)
                            "endColumnIndex": 3,  # Column C only (exclusive)
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Row 2 onwards (0-indexed)
                            "endRowIndex": 1000,  # Large range for future data
                            "startColumnIndex": 3,  # Column D (Monto a Pagar)
                            "endColumnIndex": 4,  # Column D only (exclusive)
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Row 2 onwards (0-indexed)
                            "endRowIndex": 1000,  # Large range for future data
                            "startColumnIndex": 7,  # Column H (Balance Restante)
                            "endColumnIndex": 8,  # Column H only (exclusive)
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                # Freeze header row
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
            ]
            worksheet.spreadsheet.batch_update({"requests": requests})

            self.logger.info("Applied formatting to Payment Summary worksheet")

        except Exception as e:
            raise PaymentLedgerError(f"Failed to format worksheet: {e}") from e

    def write_payment_instructions(
        self,
        worksheet: gspread.Worksheet,
        instructions: list[PaymentInstruction],
        generation_timestamp: str,
    ) -> None:
        """
        Replace worksheet content with fresh payment instructions.

        Args:
            worksheet: Target worksheet
            instructions: Payment instructions to write
            generation_timestamp: When the summary was generated

        Raises:
            PaymentLedgerError: If writing operations fail
        """
        try:
            # Clear existing payment data (keep headers)
            worksheet.clear("A2:K100")  # type: ignore[call-arg]

            if not instructions:
                # Add "No payments needed" message
                worksheet.update("A2", [["No hay pagos requeridos en este momento"]])  # type: ignore[arg-type]
                self.logger.info("No payment instructions to write")
                return

            # Prepare data rows
            data_rows = self._prepare_data_rows(instructions)

            # Write all data at once for efficiency
            if data_rows:
                range_end = f"K{len(data_rows) + 1}"
                worksheet.update(f"A2:{range_end}", data_rows)  # type: ignore[arg-type]
                self.logger.info(f"Wrote {len(data_rows)} payment instructions")

            # Add summary section
            summary_start_row = len(data_rows) + 4
            self._add_summary_section(
                worksheet, instructions, generation_timestamp, summary_start_row
            )

            # Apply conditional formatting
            self._apply_payment_conditional_formatting(worksheet, len(data_rows))

        except Exception as e:
            raise PaymentLedgerError(
                f"Failed to write payment instructions: {e}"
            ) from e

    def _prepare_data_rows(
        self, instructions: list[PaymentInstruction]
    ) -> list[list[object]]:
        """Convert payment instructions to worksheet data rows."""
        data_rows = []
        for instruction in instructions:
            row = [
                instruction["credit_card"],
                instruction["budget_id"].title(),
                -abs(float(instruction["amount_due"])),  # Raw negative number
                float(instruction["payment_amount"]),  # Raw positive number
                instruction["payment_source"],
                instruction.get("strategy_used", "priority_ordered"),
                instruction["rule_type"],
                float(instruction["remaining_balance"]),  # Raw number
                "Pendiente",  # Default status
                "",  # Date processed (empty initially)
                instruction.get("notes", ""),  # Notes
            ]
            data_rows.append(row)
        return data_rows

    def _add_summary_section(
        self,
        worksheet: gspread.Worksheet,
        instructions: list[PaymentInstruction],
        timestamp: str,
        start_row: int,
    ) -> None:
        """Add summary statistics below the payment data."""
        try:
            total_debt = sum(abs(inst["amount_due"]) for inst in instructions)
            total_payments = sum(inst["payment_amount"] for inst in instructions)
            unique_accounts = {inst["payment_source"] for inst in instructions}
            strategy_counts: dict[str, int] = {}

            # Count partial payments and remaining debt
            partial_payment_count = 0
            total_unpaid_debt = Decimal("0")

            for inst in instructions:
                strategy = inst.get("strategy_used", "priority_ordered")
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

                if inst["remaining_balance"] > 0:
                    partial_payment_count += 1
                    total_unpaid_debt += inst["remaining_balance"]

            summary_data = [
                ["RESUMEN DE PAGOS", ""],
                ["", ""],
                ["Total Deuda:", float(total_debt)],
                ["Total Pagos:", float(total_payments)],
                ["Cuentas Utilizadas:", f"{len(unique_accounts)}"],
            ]

            # Add partial payment alerts if any
            if partial_payment_count > 0:
                summary_data.extend(
                    [
                        ["", ""],
                        ["⚠️ DEUDA NO PAGADA:", float(total_unpaid_debt)],
                        ["⚠️ TARJETAS PARCIALES:", f"{partial_payment_count}"],
                    ]
                )

            summary_data.extend(
                [
                    ["", ""],
                    ["Generado el:", timestamp],
                    ["", ""],
                    ["ESTRATEGIAS UTILIZADAS:", ""],
                ]
            )

            for strategy, count in strategy_counts.items():
                summary_data.append([f"  {strategy}:", f"{count} tarjetas"])

            # Write summary
            end_row = start_row + len(summary_data) - 1
            worksheet.update(f"A{start_row}:B{end_row}", summary_data)  # type: ignore[arg-type]

            # Format summary header
            worksheet.format(
                f"A{start_row}",
                {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.8, "green": 0.9, "blue": 1.0},
                },
            )

            self.logger.info("Added summary section to worksheet")

        except Exception as e:
            self.logger.error(f"Failed to add summary section: {e}")
            raise

    def _apply_payment_conditional_formatting(
        self, worksheet: gspread.Worksheet, data_row_count: int
    ) -> None:
        """Apply conditional formatting to payment data."""
        if data_row_count == 0:
            return

        try:
            # Red background for negative balances (column C - Saldo Actual)
            worksheet.format(
                f"C2:C{data_row_count + 1}",
                {
                    "conditionalFormatRules": [
                        {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": {"userEnteredValue": "=C2<0"},
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 1.0,
                                    "green": 0.8,
                                    "blue": 0.8,
                                }
                            },
                        }
                    ]
                },
            )

            # Green background for completed payments (column I - Estado)
            worksheet.format(
                f"I2:I{data_row_count + 1}",
                {
                    "conditionalFormatRules": [
                        {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": {"userEnteredValue": "Procesado"},
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.8,
                                    "green": 1.0,
                                    "blue": 0.8,
                                }
                            },
                        }
                    ]
                },
            )

            self.logger.info("Applied conditional formatting")

        except Exception as e:
            self.logger.warning(f"Failed to apply conditional formatting: {e}")
            # Non-critical error, continue execution


def create_payment_summary(
    spreadsheet_id: str,
    instructions: list[PaymentInstruction],
    timestamp: str | None = None,
) -> None:
    """
    Convenience function to create complete payment summary.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID
        instructions: Payment instructions to write
        timestamp: Optional timestamp, defaults to current time
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    writer = PaymentLedgerWriter(spreadsheet_id)
    worksheet = writer.get_or_create_payment_worksheet()
    writer.write_payment_instructions(worksheet, instructions, timestamp)

    logger.info(f"Created payment summary with {len(instructions)} instructions")
