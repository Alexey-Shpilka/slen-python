from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class CustomerStatus(StrEnum):
    """A blocked customer's new runs are refused customer_blocked; its balance can still be moved."""

    ACTIVE = "active"
    BLOCKED = "blocked"


class CreditEntryType(StrEnum):
    """The six ways credits move; only commit is spend, and charge is the application's own debit."""

    HOLD = "hold"
    COMMIT = "commit"
    RELEASE = "release"
    TOPUP = "topup"
    ADJUST = "adjust"
    CHARGE = "charge"


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerAccount:
    """The credits of one type a customer holds (decimal strings), and the settings of that account."""

    customer_account_id: str
    customer_id: str
    project_id: str
    external_user_id: str
    credit_type: str
    balance: str
    reserved: str
    available: str
    allow_negative: bool
    low_balance_threshold: str
    created_at: datetime
    updated_at: datetime
    request_id: str | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    """An end customer of the project, with every credit account it holds."""

    customer_id: str
    external_user_id: str
    status: CustomerStatus
    blocked_at: datetime | None
    block_reason: str | None
    accounts: tuple[CustomerAccount, ...]
    created_at: datetime
    updated_at: datetime
    request_id: str | None = field(default=None, compare=False)

    def account(self, credit_type: str = "default") -> CustomerAccount | None:
        """The account of one credit type, or None while the customer holds none of it."""
        return next((held for held in self.accounts if held.credit_type == credit_type), None)

    def is_blocked(self) -> bool:
        """Whether its new runs are refused."""
        return self.status is CustomerStatus.BLOCKED


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditEntry:
    """One movement of a customer's credits, signed, with the balance it left behind."""

    entry_id: str
    customer_account_id: str
    external_user_id: str
    credit_type: str
    entry_type: CreditEntryType
    credits: str
    balance_after: str
    available_after: str
    reservation_id: str | None
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditPrice:
    """What one run of an operation holds from its customer, in credits of one type."""

    credit_price_id: str
    project_id: str
    operation_code: str
    credit_type: str
    credits: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditPriceList:
    """The price list of the project (GET /v1/credit-prices): a handful of rows, so no cursor."""

    data: tuple[CreditPrice, ...]
    request_id: str | None = field(default=None, compare=False)
