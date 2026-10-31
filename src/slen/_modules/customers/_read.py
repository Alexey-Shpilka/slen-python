from slen._http._answer import Answered
from slen._http._fields import Fields
from slen._modules.customers._types import (
    CreditEntry,
    CreditEntryType,
    CreditPrice,
    CreditPriceList,
    Customer,
    CustomerAccount,
    CustomerStatus,
)
from slen._page import Page


def account_of(fields: Fields, request_id: str | None = None) -> CustomerAccount:
    return CustomerAccount(
        customer_account_id=fields.text("customer_account_id"),
        customer_id=fields.text("customer_id"),
        project_id=fields.text("project_id"),
        external_user_id=fields.text("external_user_id"),
        credit_type=fields.text("credit_type"),
        balance=fields.text("balance"),
        reserved=fields.text("reserved"),
        available=fields.text("available"),
        allow_negative=fields.flag("allow_negative"),
        low_balance_threshold=fields.text("low_balance_threshold"),
        created_at=fields.moment("created_at"),
        updated_at=fields.moment("updated_at"),
        request_id=request_id,
    )


def customer_of(fields: Fields, request_id: str | None = None) -> Customer:
    return Customer(
        customer_id=fields.text("customer_id"),
        external_user_id=fields.text("external_user_id"),
        status=fields.choice("status", CustomerStatus),
        blocked_at=fields.nullable_moment("blocked_at"),
        block_reason=fields.nullable_text("block_reason"),
        accounts=tuple(account_of(row) for row in fields.rows("accounts")),
        created_at=fields.moment("created_at"),
        updated_at=fields.moment("updated_at"),
        request_id=request_id,
    )


def entry_of(fields: Fields) -> CreditEntry:
    return CreditEntry(
        entry_id=fields.text("entry_id"),
        customer_account_id=fields.text("customer_account_id"),
        external_user_id=fields.text("external_user_id"),
        credit_type=fields.text("credit_type"),
        entry_type=fields.choice("entry_type", CreditEntryType),
        credits=fields.text("credits"),
        balance_after=fields.text("balance_after"),
        available_after=fields.text("available_after"),
        reservation_id=fields.nullable_text("reservation_id"),
        note=fields.nullable_text("note"),
        created_at=fields.moment("created_at"),
    )


def price_of(fields: Fields) -> CreditPrice:
    return CreditPrice(
        credit_price_id=fields.text("credit_price_id"),
        project_id=fields.text("project_id"),
        operation_code=fields.text("operation_code"),
        credit_type=fields.text("credit_type"),
        credits=fields.text("credits"),
        created_at=fields.moment("created_at"),
        updated_at=fields.moment("updated_at"),
    )


def one_customer(answered: Answered) -> Customer:
    return customer_of(Fields(answered.data, "data"), answered.request_id)


def one_account(answered: Answered) -> CustomerAccount:
    return account_of(Fields(answered.data, "data"), answered.request_id)


def customer_page(answered: Answered) -> Page[Customer]:
    body = Fields(answered.data, "body")

    return Page(
        data=tuple(customer_of(row) for row in body.rows("data")),
        next_cursor=body.nested("meta").nullable_text("next_cursor"),
        request_id=answered.request_id,
    )


def entry_page(answered: Answered) -> Page[CreditEntry]:
    body = Fields(answered.data, "body")

    return Page(
        data=tuple(entry_of(row) for row in body.rows("data")),
        next_cursor=body.nested("meta").nullable_text("next_cursor"),
        request_id=answered.request_id,
    )


def price_list(answered: Answered) -> CreditPriceList:
    body = Fields(answered.data, "body")

    return CreditPriceList(data=tuple(price_of(row) for row in body.rows("data")), request_id=answered.request_id)
