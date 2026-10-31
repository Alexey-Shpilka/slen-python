import re
from dataclasses import dataclass
from typing import Final

from slen._errors import refused
from slen._http._answer import Answered, Call
from slen._http._endpoints import Endpoint
from slen._http._request import ApiRequest, Sending, encode_body
from slen._idempotency import generate_idempotency_key
from slen._modules.customers._read import customer_page, entry_page, one_account, one_customer, price_list
from slen._modules.customers._types import (
    CreditEntry,
    CreditEntryType,
    CreditPriceList,
    Customer,
    CustomerAccount,
    CustomerStatus,
)
from slen._page import Page

DEFAULT_CREDIT_TYPE: Final = "default"

# A decimal string of at most four places: credits are never a float.
CREDITS: Final = re.compile(r"-?[0-9]+(?:\.[0-9]{1,4})?")
ZERO: Final = re.compile(r"-?0+(?:\.0+)?")
EMPTY_BODY: Final = b"{}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerQuery:
    cursor: str | None
    limit: int
    search: str | None
    status: CustomerStatus | None
    credit_type: str | None
    low_balance: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryQuery:
    external_user_id: str
    cursor: str | None
    limit: int
    credit_type: str | None
    entry_type: CreditEntryType | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountSettings:
    external_user_id: str
    credit_type: str
    allow_negative: bool
    low_balance_threshold: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Move:
    endpoint: Endpoint
    external_user_id: str
    credits: str
    credit_type: str
    note: str | None
    idempotency_key: str | None


def own(external_user_id: str) -> dict[str, str]:
    return {"externalUserId": external_user_id}


def list_request(query: CustomerQuery, sending: Sending) -> ApiRequest:
    wire = {
        "view": "customers",
        "cursor": query.cursor,
        "limit": query.limit,
        "q": query.search,
        "status": query.status,
        "credit_type": query.credit_type,
        "low_balance": query.low_balance,
    }

    return ApiRequest(endpoint=Endpoint.LIST_CUSTOMERS, query=wire, envelope="page", sending=sending)


def list_call(request: ApiRequest) -> Call[Page[Customer]]:
    return Call(request, customer_page)


def entries_request(query: EntryQuery, sending: Sending) -> ApiRequest:
    wire = {
        "cursor": query.cursor,
        "limit": query.limit,
        "credit_type": query.credit_type,
        "entry_type": query.entry_type,
    }

    return ApiRequest(
        endpoint=Endpoint.ENTRIES,
        params=own(query.external_user_id),
        query=wire,
        envelope="page",
        sending=sending,
    )


def entries_call(request: ApiRequest) -> Call[Page[CreditEntry]]:
    return Call(request, entry_page)


def customer_call(endpoint: Endpoint, external_user_id: str, sending: Sending) -> Call[Customer]:
    # `get` sends no body; `create` and `unblock` send `{}`.
    body = None if endpoint is Endpoint.GET_CUSTOMER else EMPTY_BODY
    request = ApiRequest(endpoint=endpoint, params=own(external_user_id), body=body, sending=sending)

    return Call(request, one_customer)


def block_call(external_user_id: str, reason: str | None, sending: Sending) -> Call[Customer]:
    body = EMPTY_BODY if reason is None else encode_body(Endpoint.BLOCK, {"reason": reason})
    request = ApiRequest(endpoint=Endpoint.BLOCK, params=own(external_user_id), body=body, sending=sending)

    return Call(request, one_customer)


def nothing(answered: Answered) -> None:
    return None


# A repeat after no answer that finds no customer: the attempt that got no answer deleted it.
def delete_call(external_user_id: str, sending: Sending) -> Call[None]:
    request = ApiRequest(
        endpoint=Endpoint.DELETE_CUSTOMER,
        params=own(external_user_id),
        sending=sending,
        wants_body=False,
        done_after_no_answer="customer_not_found",
    )

    return Call(request, nothing)


# The whole of an account's settings: what is left out goes back to its default.
def account_call(settings: AccountSettings, sending: Sending) -> Call[CustomerAccount]:
    body = {"allow_negative": settings.allow_negative, "low_balance_threshold": settings.low_balance_threshold}
    request = ApiRequest(
        endpoint=Endpoint.UPDATE_ACCOUNT,
        params={**own(settings.external_user_id), "creditType": settings.credit_type},
        body=encode_body(Endpoint.UPDATE_ACCOUNT, body),
        sending=sending,
    )

    return Call(request, one_account)


def move_call(move: Move, sending: Sending) -> Call[CustomerAccount]:
    refuse_credits(move)

    # An empty credit type would be read as `default`: credits would move on another account.
    if not isinstance(move.credit_type, str) or not move.credit_type.strip():
        raise refused(f"Slen: the credit_type of {move.endpoint} is empty; pass one that is not, or none for default.")

    body: dict[str, object] = {"credits": move.credits, "credit_type": move.credit_type}
    body.update({"note": move.note} if move.note is not None else {})
    request = ApiRequest(
        endpoint=move.endpoint,
        params=own(move.external_user_id),
        body=encode_body(move.endpoint, body),
        idempotency_key=generate_idempotency_key() if move.idempotency_key is None else move.idempotency_key,
        sending=sending,
    )

    return Call(request, one_account)


def refuse_credits(move: Move) -> None:
    credits: object = move.credits
    decimal = isinstance(credits, str) and CREDITS.fullmatch(credits) is not None and ZERO.fullmatch(credits) is None
    signed = move.endpoint is Endpoint.ADJUST

    if decimal and (signed or not str(credits).startswith("-")):
        return

    what = "a signed decimal string other than zero" if signed else "a decimal string above zero"

    raise refused(
        f"Slen: the credits of {move.endpoint} must be {what}, with at most four decimal places, as '25.5' is."
    )


def prices_call(operation_code: str | None, credit_type: str | None, sending: Sending) -> Call[CreditPriceList]:
    query = {"operation_code": operation_code, "credit_type": credit_type}
    request = ApiRequest(endpoint=Endpoint.PRICES, query=query, envelope="list", sending=sending)

    return Call(request, price_list)
