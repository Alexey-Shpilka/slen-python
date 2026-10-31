import asyncio
from typing import Any

import httpx
import pytest

from slen import (
    AsyncSlen,
    CreditEntryType,
    CustomerNotFoundError,
    CustomerStatus,
    InvalidRequestError,
    InvalidResponseError,
    Slen,
)
from slen.testing import FakeTransport
from support.harness import (
    BASE,
    KEY,
    Kind,
    account,
    collect,
    customer,
    data,
    drive,
    entry,
    price,
    raised,
)

USER = "user 42"


def page(rows: list[Any], cursor: str | None, limit: int = 2) -> dict[str, Any]:
    return {"data": rows, "meta": {"limit": limit, "next_cursor": cursor}}


def query_of(url: str) -> dict[str, str]:
    return dict(httpx.URL(url).params.multi_items())


def test_list_always_sends_the_view_and_the_limit(kind: Kind) -> None:
    fake = FakeTransport().push(200, page([customer()], None, 50))

    found = drive(kind, fake, lambda slen: slen.customers.list())

    assert fake.last().url == f"{BASE}/v1/customers?view=customers&limit=50"
    assert found.next_cursor is None
    assert found.data[0].external_user_id == USER


def test_list_sends_every_filter_by_its_wire_name(kind: Kind) -> None:
    fake = FakeTransport().push(200, page([], None, 30))

    drive(
        kind,
        fake,
        lambda slen: slen.customers.list(
            cursor="eyJpZCI6MX0",
            limit=30,
            search="user",
            status=CustomerStatus.ACTIVE,
            credit_type="enrichment",
            low_balance="10",
        ),
    )

    assert query_of(fake.last().url) == {
        "view": "customers",
        "cursor": "eyJpZCI6MX0",
        "limit": "30",
        "q": "user",
        "status": "active",
        "credit_type": "enrichment",
        "low_balance": "10",
    }


def test_get_create_block_unblock_and_delete_send_the_wire_of_the_other_sdks(kind: Kind) -> None:
    fake = FakeTransport()
    fake.push(200, data(customer())).push(201, data(customer(accounts=[])))
    fake.push(200, data(customer(status="blocked"))).push(200, data(customer(status="blocked")))
    fake.push(200, data(customer())).push(204)

    drive(kind, fake, lambda slen: slen.customers.get(USER))
    drive(kind, fake, lambda slen: slen.customers.create(USER))
    drive(kind, fake, lambda slen: slen.customers.block(USER, reason="chargeback"))
    blocked = drive(kind, fake, lambda slen: slen.customers.block(USER))
    drive(kind, fake, lambda slen: slen.customers.unblock(USER))
    gone = drive(kind, fake, lambda slen: slen.customers.delete(USER))

    wire = [(request.method, request.url.removeprefix(BASE), request.body) for request in fake.requests]
    assert wire == [
        ("GET", "/v1/customers/user%2042", None),
        ("PUT", "/v1/customers/user%2042", {}),
        ("POST", "/v1/customers/user%2042/block", {"reason": "chargeback"}),
        ("POST", "/v1/customers/user%2042/block", {}),
        ("POST", "/v1/customers/user%2042/unblock", {}),
        ("DELETE", "/v1/customers/user%2042", None),
    ]
    assert blocked.is_blocked()
    assert gone is None


def test_update_account_puts_the_whole_settings(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(account(allow_negative=True))).push(200, data(account()))

    drive(
        kind,
        fake,
        lambda slen: slen.customers.update_account(
            USER, "enrichment", allow_negative=True, low_balance_threshold="10.0000"
        ),
    )
    drive(kind, fake, lambda slen: slen.customers.update_account(USER, "enrichment"))

    assert [request.body for request in fake.requests] == [
        {"allow_negative": True, "low_balance_threshold": "10.0000"},
        {"allow_negative": False, "low_balance_threshold": "0"},
    ]
    assert fake.last().url == f"{BASE}/v1/customers/user%2042/accounts/enrichment"


@pytest.mark.parametrize(("movement", "path"), [("top_up", "topup"), ("charge", "charge"), ("adjust", "adjust")])
def test_a_movement_always_sends_its_credit_type(kind: Kind, movement: str, path: str) -> None:
    fake = FakeTransport().push(200, data(account())).push(200, data(account()))

    drive(kind, fake, lambda slen: getattr(slen.customers, movement)(USER, "5.25", idempotency_key="invoice-1"))
    drive(
        kind,
        fake,
        lambda slen: getattr(slen.customers, movement)(USER, "5", credit_type="enrichment", note="Invoice 7781"),
    )

    first, second = fake.requests
    assert first.url == f"{BASE}/v1/customers/user%2042/{path}"
    assert first.body == {"credits": "5.25", "credit_type": "default"}
    assert first.headers["idempotency-key"] == "invoice-1"
    assert second.body == {"credits": "5", "credit_type": "enrichment", "note": "Invoice 7781"}
    assert second.headers["idempotency-key"] != first.headers["idempotency-key"]


@pytest.mark.parametrize(
    ("movement", "credits"),
    [
        ("top_up", "0"),
        ("top_up", "-5"),
        ("top_up", "5.12345"),
        ("top_up", "5,5"),
        ("charge", "-0.0001"),
        ("charge", "5\n"),
        ("charge", "\u0665"),
        ("adjust", "0.0000"),
        ("adjust", "-0"),
        ("adjust", 5),
    ],
)
def test_credits_of_the_wrong_form_are_refused_before_the_wire(kind: Kind, movement: str, credits: object) -> None:
    fake = FakeTransport()

    error = raised(kind, fake, lambda slen: getattr(slen.customers, movement)(USER, credits))

    assert isinstance(error, InvalidRequestError)
    assert "four decimal places" in str(error)
    assert fake.requests == ()


def test_an_adjustment_may_be_negative_and_an_empty_credit_type_is_refused(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(account()))

    drive(kind, fake, lambda slen: slen.customers.adjust(USER, "-3.0000"))
    error = raised(kind, fake, lambda slen: slen.customers.charge(USER, "1", credit_type=""))

    assert isinstance(error, InvalidRequestError)
    assert "credit_type" in str(error)
    assert len(fake.requests) == 1


@pytest.mark.parametrize("value", ["", "   ", None, 42])
def test_an_empty_path_value_is_refused_before_the_wire(kind: Kind, value: object) -> None:
    fake = FakeTransport()

    error = raised(kind, fake, lambda slen: slen.customers.get(value))

    assert isinstance(error, InvalidRequestError)
    assert "externalUserId" in str(error)
    assert fake.requests == ()


def test_entries_and_prices_send_their_filters(kind: Kind) -> None:
    fake = FakeTransport().push(200, page([entry()], None, 30)).push(200, data([price()]))

    statement = drive(
        kind,
        fake,
        lambda slen: slen.customers.entries(
            USER, cursor="c0", limit=30, credit_type="enrichment", entry_type=CreditEntryType.CHARGE
        ),
    )
    prices = drive(
        kind, fake, lambda slen: slen.customers.prices(operation_code="support.answer", credit_type="default")
    )

    first, second = fake.requests
    assert query_of(first.url) == {"cursor": "c0", "limit": "30", "credit_type": "enrichment", "entry_type": "charge"}
    assert query_of(second.url) == {"operation_code": "support.answer", "credit_type": "default"}
    assert statement.data[0].entry_type is CreditEntryType.CHARGE
    assert prices.data[0].credits == "2.0000"


def test_a_customer_names_its_accounts(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(customer()))

    found = drive(kind, fake, lambda slen: slen.customers.get(USER))

    assert found.account() is not None
    assert found.account("enrichment") is None
    assert found.status is CustomerStatus.ACTIVE


def test_delete_after_no_answer_reads_a_404_of_no_customer_as_done(kind: Kind) -> None:
    fake = FakeTransport().push_exception(httpx.ConnectError("refused"))
    fake.push(404, {"error": {"code": "customer_not_found", "message": "Not found"}})

    assert drive(kind, fake, lambda slen: slen.customers.delete(USER)) is None
    assert len(fake.requests) == 2


def test_delete_of_a_customer_that_never_was_is_customer_not_found(kind: Kind) -> None:
    fake = FakeTransport().push(404, {"error": {"code": "customer_not_found", "message": "Not found"}})

    assert isinstance(raised(kind, fake, lambda slen: slen.customers.delete(USER)), CustomerNotFoundError)


def test_a_page_without_its_cursor_is_an_invalid_response(kind: Kind) -> None:
    fake = FakeTransport().push(200, {"data": []})

    assert isinstance(raised(kind, fake, lambda slen: slen.customers.list()), InvalidResponseError)


# ---------------------------------------------------------------------------
# Every page.


def full_pages() -> FakeTransport:
    fake = FakeTransport()
    fake.push(200, page([entry(entry_id="1"), entry(entry_id="2")], "c1"))
    fake.push(200, page([entry(entry_id="3"), entry(entry_id="4")], "c2"))
    fake.push(200, page([], None))

    return fake


def test_entries_all_reads_every_page_with_the_cursor_of_the_one_before(kind: Kind) -> None:
    fake = full_pages()

    rows = drive(kind, fake, lambda slen: collect(slen.customers.entries_all(USER, limit=2)))

    assert [row.entry_id for row in rows] == ["1", "2", "3", "4"]
    assert [query_of(request.url).get("cursor") for request in fake.requests] == [None, "c1", "c2"]
    assert {query_of(request.url)["limit"] for request in fake.requests} == {"2"}


def test_list_all_starts_at_the_cursor_it_is_given(kind: Kind) -> None:
    fake = FakeTransport().push(200, page([customer()], "c1", 1)).push(200, page([], None, 1))

    rows = drive(kind, fake, lambda slen: collect(slen.customers.list_all(cursor="c0", limit=1, search="user")))

    assert len(rows) == 1
    assert [query_of(request.url)["cursor"] for request in fake.requests] == ["c0", "c1"]
    assert {query_of(request.url)["q"] for request in fake.requests} == {"user"}


def test_nothing_is_sent_before_the_first_row_and_a_break_sends_nothing_more() -> None:
    fake = full_pages()
    rows = Slen(api_key=KEY, http_client=httpx.Client(transport=fake)).customers.entries_all(USER, limit=2)

    assert fake.requests == ()

    for _ in rows:
        break

    assert len(fake.requests) == 1


def test_nothing_is_sent_before_the_first_row_of_an_async_loop() -> None:
    fake = full_pages()

    async def first_only() -> None:
        rows = AsyncSlen(api_key=KEY, http_client=httpx.AsyncClient(transport=fake)).customers.entries_all(USER)

        assert fake.requests == ()

        async for _ in rows:
            break

    asyncio.run(first_only())

    assert len(fake.requests) == 1


def test_a_cursor_that_comes_back_as_it_was_sent_ends_the_loop_after_its_rows(kind: Kind) -> None:
    fake = FakeTransport().push(200, page([entry(entry_id="1")], "c1")).push(200, page([entry(entry_id="2")], "c1"))
    seen: list[str] = []

    error = raised(kind, fake, lambda slen: keep(slen.customers.entries_all(USER), seen))

    assert isinstance(error, InvalidResponseError)
    assert "the cursor it was asked for" in str(error)
    assert seen == ["1", "2"]


def keep(rows: Any, seen: list[str]) -> Any:
    if hasattr(rows, "__anext__"):

        async def each() -> None:
            async for row in rows:
                seen.append(row.entry_id)

        return each()

    for row in rows:
        seen.append(row.entry_id)

    return None


def test_a_loop_takes_no_request_id_and_sends_nothing(kind: Kind) -> None:
    fake = FakeTransport()

    with pytest.raises(TypeError):
        drive(kind, fake, lambda slen: slen.customers.list_all(request_id="order-42:list"))

    with pytest.raises(TypeError):
        drive(kind, fake, lambda slen: slen.customers.entries_all(USER, request_id="order-42:list"))

    assert fake.requests == ()


def test_a_loop_checks_its_arguments_at_the_call(kind: Kind) -> None:
    fake = FakeTransport()

    with pytest.raises(InvalidRequestError):
        drive(kind, fake, lambda slen: slen.customers.entries_all("", limit=2))

    with pytest.raises(InvalidRequestError):
        drive(kind, fake, lambda slen: slen.customers.list_all(timeout=-1))

    assert fake.requests == ()


class Timeouts(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Answers two pages and keeps the read timeout each request was sent with."""

    def __init__(self) -> None:
        self.reads: list[object] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.reads.append(request.extensions["timeout"]["read"])
        cursor = None if self.reads[1:] else "c1"

        return httpx.Response(200, json=page([entry()], cursor))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handle_request(request)


def test_the_timeout_of_a_loop_holds_for_every_page(kind: Kind) -> None:
    transport = Timeouts()

    drive(kind, transport, lambda slen: collect(slen.customers.entries_all(USER, timeout=7.5)))

    assert transport.reads == [7.5, 7.5]


def test_the_retries_of_a_loop_hold_for_every_page(kind: Kind) -> None:
    unavailable = {"error": {"code": "service_unavailable"}}
    fake = FakeTransport().push(200, page([entry()], "c1")).push(503, unavailable)

    error = raised(kind, fake, lambda slen: collect(slen.customers.entries_all(USER, retries=0)))

    assert error.__class__.__name__ == "ServiceUnavailableError"
    assert len(fake.requests) == 2
