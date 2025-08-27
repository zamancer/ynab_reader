from typing import Any, TypedDict


class YNABEntry(TypedDict):
    name: str
    balance: float
    consolidated: bool


class YNABAccount(TypedDict):
    name: str
    balance: float
    account_type: str  # "credit_card", "checking", "savings"
    budget_id: str
    consolidated: bool
    payment_due_date: int | None  # Day of month (1-31) from "Fecha Pago" column


class PaymentRule(TypedDict):
    credit_card_name: str
    budget_id: str  # "main" or "secondary"
    debit_sources: list[str]  # Priority-ordered payment sources
    strategy: str | None  # Payment strategy name, defaults to "priority_ordered"
    strategy_config: dict[str, Any] | None  # Strategy-specific configuration


class PaymentConfig(TypedDict):
    default_payment_sources: dict[str, list[str]]  # budget_id -> default sources
    payment_rules: list[PaymentRule]
    global_strategy_defaults: dict[str, dict[str, Any]] | None  # Strategy defaults


class PaymentInstruction(TypedDict):
    """Represents a single transfer instruction from one source account to pay a credit card"""
    credit_card: str
    budget_id: str
    amount_due: float  # Total credit card debt
    payment_source: str  # Source account name
    payment_amount: float  # Amount to transfer from this source
    remaining_balance: float  # Remaining card balance after this transfer
    payment_due_date: int | None  # Day of month
    days_until_due: int  # For urgency calculation
    rule_type: str  # "explicit" or "default"
    strategy_used: str
    notes: str  # e.g., "Transfer 1 of 2"
