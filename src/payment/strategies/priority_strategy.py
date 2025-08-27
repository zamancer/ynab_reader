"""
Priority-ordered payment strategy implementation.
Handles priority-based payment calculations only.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.payment.strategies.base_strategy import PaymentStrategy, PaymentStrategyError
from src.ynab.ynab_types import PaymentInstruction, PaymentRule, YNABAccount

logger = logging.getLogger(__name__)


class PriorityOrderedStrategy(PaymentStrategy):
    """Pay using debit sources in priority order until full balance is covered."""

    def calculate_payments(
        self,
        credit_card: YNABAccount,
        available_sources: list[YNABAccount],
        rule: PaymentRule,
        strategy_config: dict[str, Any],
    ) -> list[PaymentInstruction]:
        """
        Calculate payments using priority-ordered sources.

        Attempts to pay the full credit card balance by using debit sources
        in the priority order specified in the rule, respecting minimum
        balance constraints.

        Args:
            credit_card: Credit card account to pay (should have negative balance)
            available_sources: Available debit accounts for payment
            rule: Payment rule with prioritized debit_sources list
            strategy_config: Configuration including min_balance, max_payment_per_source

        Returns:
            List of PaymentInstructions, one per source account used

        Raises:
            PaymentStrategyError: If calculation fails due to invalid inputs
        """
        try:
            target_amount = abs(credit_card["balance"])
            if target_amount == Decimal("0"):
                logger.info(f"Credit card {credit_card['name']} has no debt to pay")
                return []

            remaining_debt = target_amount
            instructions: list[PaymentInstruction] = []

            # Sort sources by rule priority
            ordered_sources = self._sort_by_priority(
                available_sources, rule["debit_sources"]
            )

            logger.info(
                f"Calculating payments for {credit_card['name']}: ${target_amount}"
            )
            logger.info(f"Using {len(ordered_sources)} sources in priority order")

            for i, source in enumerate(ordered_sources):
                if remaining_debt <= Decimal("0"):
                    break

                # Calculate available amount from this source
                min_balance = Decimal(str(strategy_config.get("min_balance", 0)))
                max_payment = strategy_config.get("max_payment_per_source")

                available_amount = max(Decimal("0"), source["balance"] - min_balance)

                if max_payment is not None:
                    available_amount = min(available_amount, Decimal(str(max_payment)))

                payment_amount = min(remaining_debt, available_amount)

                if payment_amount > Decimal("0"):
                    instruction = self._create_payment_instruction(
                        credit_card=credit_card,
                        source=source,
                        payment_amount=payment_amount,
                        remaining_debt=remaining_debt - payment_amount,
                        target_amount=target_amount,
                        transfer_number=i + 1,
                        total_transfers=len(ordered_sources),
                        rule=rule,
                    )
                    instructions.append(instruction)
                    remaining_debt -= payment_amount

                    logger.info(
                        f"Transfer {i + 1}: ${payment_amount} from {source['name']}"
                    )

            # Log final result
            if remaining_debt > Decimal("0"):
                logger.warning(
                    f"Partial payment: ${remaining_debt} remaining on {credit_card['name']}"
                )
            else:
                logger.info(f"Full payment calculated for {credit_card['name']}")

            return instructions

        except Exception as e:
            logger.error(
                f"Payment calculation failed for {credit_card.get('name', 'unknown')}: {e}"
            )
            raise PaymentStrategyError(
                f"Priority strategy calculation failed: {e}"
            ) from e

    def get_strategy_name(self) -> str:
        """Return strategy identifier."""
        return "priority_ordered"

    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate priority strategy configuration.

        Args:
            config: Strategy configuration dictionary

        Returns:
            True if configuration is valid

        Raises:
            PaymentStrategyError: If configuration is invalid
        """
        try:
            # Validate min_balance if present
            if "min_balance" in config:
                min_balance = config["min_balance"]
                if (
                    not isinstance(min_balance, int | float | Decimal)
                    or min_balance < 0
                ):
                    raise PaymentStrategyError(
                        "min_balance must be non-negative number"
                    )

            # Validate max_payment_per_source if present
            if "max_payment_per_source" in config:
                max_payment = config["max_payment_per_source"]
                if (
                    not isinstance(max_payment, int | float | Decimal)
                    or max_payment <= 0
                ):
                    raise PaymentStrategyError(
                        "max_payment_per_source must be positive number"
                    )

            return True

        except Exception as e:
            raise PaymentStrategyError(f"Configuration validation failed: {e}") from e

    def _sort_by_priority(
        self, available_sources: list[YNABAccount], priority_list: list[str]
    ) -> list[YNABAccount]:
        """
        Sort available sources by priority order defined in rule.

        Args:
            available_sources: List of available debit accounts
            priority_list: Ordered list of source names from payment rule

        Returns:
            List of sources sorted by priority (first = highest priority)
        """
        # Create mapping for quick lookup
        source_map = {source["name"]: source for source in available_sources}
        ordered_sources = []

        # Add sources in priority order
        for priority_name in priority_list:
            if priority_name in source_map:
                ordered_sources.append(source_map[priority_name])

        # Add any remaining sources not in priority list (as fallback)
        remaining_sources = [
            source
            for source in available_sources
            if source["name"] not in priority_list
        ]
        ordered_sources.extend(remaining_sources)

        logger.debug(f"Priority order: {[s['name'] for s in ordered_sources]}")
        return ordered_sources

    def _create_payment_instruction(
        self,
        credit_card: YNABAccount,
        source: YNABAccount,
        payment_amount: Decimal,
        remaining_debt: Decimal,
        target_amount: Decimal,
        transfer_number: int,
        total_transfers: int,
        rule: PaymentRule,
    ) -> PaymentInstruction:
        """
        Create a PaymentInstruction for a single transfer.

        Args:
            credit_card: The credit card being paid
            source: The debit account providing funds
            payment_amount: Amount to transfer from this source
            remaining_debt: Remaining debt after this transfer
            target_amount: Total original debt amount
            transfer_number: Which transfer this is (1-based)
            total_transfers: Total number of transfers needed
            rule: Payment rule used

        Returns:
            PaymentInstruction with all required fields populated
        """
        # Calculate days until due (if due date is available)
        days_until_due = 0
        if credit_card.get("payment_due_date"):
            today = datetime.now().day
            due_date = credit_card["payment_due_date"]
            # Simple calculation - could be enhanced for month boundaries
            if due_date is not None:
                days_until_due = max(0, due_date - today)

        # Generate descriptive notes
        notes = ""
        if total_transfers > 1:
            notes = f"Transfer {transfer_number} of {total_transfers}"

        if remaining_debt > Decimal("0"):
            if not notes:
                notes = "PAGO PARCIAL: Fondos insuficientes"
            else:
                notes += f" - ALERTA: Saldo restante ${remaining_debt:,.2f}"

        return PaymentInstruction(
            credit_card=credit_card["name"],
            budget_id=credit_card["budget_id"],
            amount_due=target_amount,
            payment_source=source["name"],
            payment_amount=payment_amount,
            remaining_balance=remaining_debt,
            payment_due_date=credit_card.get("payment_due_date"),
            days_until_due=days_until_due,
            rule_type=rule.get("rule_origin", "default"),
            strategy_used=self.get_strategy_name(),
            notes=notes,
        )
