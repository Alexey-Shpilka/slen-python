# Slen Python SDK

`slen` runs your flows and reads how they ended, keeps your end customers and their credits, and checks the webhooks Slen sends you.

- **Two clients**, `Slen` for threads and `AsyncSlen` for asyncio, with the same calls.
- **One dependency**, [httpx](https://www.python-httpx.org/). OpenTelemetry is an extra, `slen[otel]`.
- Answers are frozen dataclasses with the wire's field names (`execution_id`, `error_code`); statuses are `StrEnum`s, times `datetime`s with their offset, money and credits decimal strings — never floats. Typed (`py.typed`), checked with mypy `--strict` and pyright strict.

> Not published yet: the package goes to PyPI with the first release.

## Install

```bash
pip install slen
```

## Compatibility

| | Versions | Held by |
|---|---|---|
| Python | 3.11 and newer | the suite on 3.11, 3.12, 3.13 and 3.14 |
| httpx | 0.27 and newer, below 1 | the suite on 0.27.0, and on the newest every week |
| OpenTelemetry | `opentelemetry-api` 1.27 and newer, optional | only `slen.otel` needs it: `pip install "slen[otel]"` |
| Types | mypy `--strict`, pyright strict | the help examples checked against the installed package |

## The client

```python
from slen import Slen

slen = Slen()
```

The key is the project's API key; left out, it is read from `SLEN_API_KEY`, and no other variable is read. The client talks to the hosted API. Building it checks the options and touches no network: a missing key is a `ValueError`, an option of the wrong type a `TypeError`, a timeout or a retry count out of range a `ValueError`.

| Option | Default | |
|---|---|---|
| `api_key` | `SLEN_API_KEY` | the project's key, `sl_live_…` |
| `timeout` | `65.0` | how long one attempt may take, in seconds; `math.inf` switches the clock off |
| `connect_timeout` | `5.0` | how long connecting may take |
| `retries` | `2` | attempts after the first when there is no answer, a 429 or a 503 |
| `logger` | the `slen` logger | the journal of the SDK — below |
| `span_recorder` | none | where spans go — below |
| `webhook_secret`, `webhook_tolerance_seconds` | none, `300` | for checking webhooks — below |
| `http_client` | one the SDK builds | an `httpx.Client` of yours (`httpx.AsyncClient` for `AsyncSlen`); the SDK does not close it |
| `headers` | none | sent with every request; the SDK's own headers win over yours |

**How a call is written.** What names the thing is positional — an operation and its input, an execution id, an external user id, an amount of credits — and everything else is a keyword argument. Every call that goes to the API also takes `timeout` (a clock for each attempt of that call in place of the client's), `retries` (how often that call is sent again; `0` sends it once) and `request_id` (your own id of the request — below); a call that moves money takes `idempotency_key`. `executions.wait()` takes `timeout_seconds` and `on_poll_error`, and gives each of its reads what is left of its time.

`with Slen() as slen:` closes the connections when the block ends, and so does `slen.close()`. The SDK passes its own timeout on every request, so an `httpx.Client` of yours built without one is not cut at httpx's five seconds.

## Run a flow

A flow is run by the code of the operation it is bound to. A flow with a model node reads the conversation from `input["messages"]`.

```python
run = slen.operations.execute(
    "support.reply",
    {"messages": [{"role": "user", "content": "Where is my order?"}]},
    customer="user_8421",
    idempotency_key="ticket-42:reply",
)

print(run.status)  # queued | waiting | running | completed | rejected | failed | uncertain

if run.is_completed() and run.output is not None:
    print(run.output["content"])
```

- `customer` is the end customer the run is for, and pays in their credits (`context["user_id"]`); `credit_type` names their account (`context["credit_type"]`). Anything else the flow reads goes in `context`; a `user_id` there that is not `customer` is refused before the wire.
- **The idempotency key is yours to choose**, derived from the unit of work (`ticket-42:reply`). The server runs a key once: a second request under it runs nothing and answers with that run as it is now (`replayed` is true). Without a key the SDK makes one up, which covers its own retries and nothing else. For a job of your own queue, `idempotency_key_for_job(job_id, "support.reply")` gives every attempt of the job the same key.
- **A refusal is an answer or an error, depending on the flow.** A `reject` node answers with `status` `rejected` and its code in `error_code` (`run.is_rejected()`); a refusal of the platform the flow did not route is raised (below). `failed` and `uncertain` are runs that broke — read `error_code`, and `error_message` to show or log.
- `is_completed()`, `is_rejected()`, `is_pending()` (`queued`, `waiting`, `running`) and `is_finished()` (anything else) read the status, as in the other SDKs. A status prints as the wire spells it, and equals that string.
- The money of the run's model calls is held and settled inside the flow. `cost.estimated` is known when a model call was authorized; `cost.actual` arrives a minute or two after the run ended, so the answer of a run that has just finished carries `None` there.

`execute_async()` takes the same arguments and answers at once with `status` `queued`, for a run that goes on in the background.

## Wait for a run

```python
from slen import SlenError


def told(error: SlenError, failures_in_a_row: int) -> None:
    print(error.code, failures_in_a_row)


queued = slen.operations.execute_async(
    "report.summarize",
    {"messages": [{"role": "user", "content": "Summarize the third-quarter report."}]},
    idempotency_key="report-2026-q3:summary",
)

finished = slen.executions.wait(queued.execution_id, timeout_seconds=120, on_poll_error=told)
```

`wait()` reads the run until it is over, at the pace the server asks for (`retry_after_seconds`; otherwise 1 s doubling up to 30 s). When the time is up it answers the last state it read, which may still be pending — that is not an error. A read that gets no answer, a 429 or a 5xx is told to `on_poll_error` and the wait goes on; any other failure is raised at once, and so is what `on_poll_error` raises. `timeout_seconds` defaults to 300; `math.inf` waits without a ceiling and gives up after ten failed reads in a row.

`slen.executions.get(execution_id)` reads the run once; `slen.executions.trace(execution_id)` reads the nodes it walked and its events.

## End customers

A customer is your own user, named by your own opaque id (`external_user_id` — not an email address). Their credits sit in one account per credit type.

```python
slen.customers.create("user_8421")
slen.customers.top_up("user_8421", "100.0000", note="Invoice 7781", idempotency_key="invoice-7781:topup")

customer = slen.customers.get("user_8421")
account = slen.customers.charge("user_8421", "5.0000", note="PDF export", idempotency_key="export-991:charge")
```

| Call | What it does |
|---|---|
| `list(cursor=, limit=, search=, status=, credit_type=, low_balance=)` | customers with their accounts, a page at a time (`data`, `next_cursor`) |
| `list_all(cursor=, limit=, …)` | every customer `list()` reads, page after page — below |
| `get(id)`, `create(id)` | one customer with every account; `create()` is idempotent and moves no credits |
| `update_account(id, credit_type, allow_negative=, low_balance_threshold=)` | the settings of one account; what is left out goes back to `False` and `"0"` |
| `block(id, reason=)`, `unblock(id)` | a blocked customer's new runs are refused (`CustomerBlockedError`); their balance can still be settled |
| `delete(id)` | a customer with no history; one with history is refused (409) — block them instead |
| `top_up(id, credits)`, `charge(id, credits)` | add credits; take them for a service of your own application. Above zero |
| `adjust(id, credits)` | an operator's correction, with a sign; not zero |
| `entries(id, cursor=, limit=, credit_type=, entry_type=)` | the statement of the customer's accounts, a page at a time |
| `entries_all(id, cursor=, limit=, …)` | every entry of the statement, page after page |
| `prices(operation_code=, credit_type=)` | what an operation costs in credits: `data`, a handful of rows, no cursor |

Credits are a decimal string of at most four places (`"5"`, `"5.25"`, `"-3.0000"`); anything else is refused before the wire. A movement takes `credit_type` (default `"default"`), `note` and `idempotency_key`; under the same key the server moves the credits once.

**Every page.** `list_all()` and `entries_all()` answer an iterator — an async one on `AsyncSlen`, read with `async for`:

```python
for entry in slen.customers.entries_all("user_8421", limit=100):
    print(entry.entry_type, entry.credits)
```

The arguments are checked at the call; nothing is sent until the loop asks for the first row, and each page is one request, sent when the loop reaches it, so a `break` sends nothing more. `cursor` is where the loop starts, `limit` the size of a page (1 to 100, 50 by default), and `timeout` and `retries` hold for each page. When the rows end exactly at the end of a page, the loop reads one empty page to find out — the API's cursor works that way. A cursor that comes back as it was sent is an `InvalidResponseError`, not an endless loop. To pick up later where you stopped, keep `next_cursor` of a page from `list()` or `entries()` and pass it as `cursor`.

## Webhooks

```python
from slen import ExecutionFinishedEvent, Webhooks

webhooks = Webhooks(secret="whsec_…")


def receive(body: bytes, signature: str | None) -> None:
    event = webhooks.construct_event(body, signature)

    if isinstance(event, ExecutionFinishedEvent):
        print(event.data.execution_id, event.data.status)
```

`construct_event()` checks the `Slen-Signature` header against the raw body — exactly the bytes that arrived, as `bytes` or `str` (`await request.body()` in FastAPI, `request.body` in Django) — and reads the event. A signature that does not hold is a `WebhookSignatureError` whose `reason` says which check refused it (`missing_header`, `malformed_header`, `outside_tolerance`, `no_matching_signature`): answer 400 and do nothing with the body. A signed body that is not an event is an `InvalidResponseError` (`webhook_payload_invalid`). `verify()` answers `True` or `False` and reads nothing.

`execution.finished`, `customer.balance_low`, `approval.requested` and `approval.decided` are typed (`ExecutionFinishedEvent` and the rest; `isinstance()` or `match` tells them apart). Every other event arrives as an `UnknownWebhookEvent` with its `data` as it was sent. A receiver needs the endpoint's signing secret, not an API key: `Webhooks` takes it and needs no client, and `slen.webhooks` uses the `webhook_secret` of the client unless the call names one. A signature older than the tolerance (300 seconds) is refused; `tolerance_seconds` and `now` of a call change that for one check. A secret that is empty, or none at all, is a `ValueError` before anything is checked.

## The journal

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)

slen = Slen(logger=logging.getLogger("billing.slen"))
```

The journal goes to the standard library's `logging`: the `slen` logger by default, which drops every record until your application configures it, or the `logger=` you give — a `logging.Logger`, a `LoggerAdapter`, or anything with `debug`, `info`, `warning` and `error`. Each event is a record whose message is the name of the event (`LOG_EVENTS`), and whose fields are attributes of the record (`extra`), so a JSON formatter writes them as fields — the PHP and TypeScript SDKs write the same names with the same fields. Before Python 3.13 a `LoggerAdapter` replaces the `extra` of each call with its own, and the SDK's fields are lost; on 3.13 and later pass it `merge_extra=True`, before that use an adapter whose `process()` merges the two, as the `RequestLog` of the FastAPI and Django help examples does:

| Event | Level | When |
|---|---|---|
| `slen.request`, `slen.response` | debug | every attempt; the answer, with `status`, `duration_ms` and `request_id` |
| `slen.retry` | warning | an attempt that is repeated: `reason` `no_answer`, `rate_limited` or `unavailable`, `delay_ms` |
| `slen.refused` | info | a 4xx |
| `slen.unauthorized` | error | a 401, or a 403 about the key |
| `slen.failed` | error | a 5xx, an unreadable answer, or no answer after every attempt — with `error_type` |
| `slen.wait.poll`, `slen.wait.poll_failed` | debug, warning | the reads of a wait |
| `slen.webhook.rejected` | warning | a webhook refused, with `reason` |

A request is written by its route — `POST /v1/customers/{externalUserId}/charge`, never the values in it. The journal never carries the API key, the webhook secret, an idempotency key, a body, the server's error message, or a value of the path or the query. A logger that raises does not fail the call.

**httpx writes a journal of its own**: at `INFO`, the logger `httpx` writes every request with its whole URL, an external user id in it. Raise that logger to `WARNING` in your application, as above, unless you want those lines.

```python
slen_of_this_request = slen.with_logger(request_logger)
```

`with_logger()` answers a copy of the client that writes to another logger — one that carries the id of the request your server is handling, say. It sends through the same connections and records into the same span recorder; the client it was made from is not changed, and the copy owns no connections, so closing it closes nothing.

## Spans

A run leaves one span: `operations.execute`, `operations.execute_async`, or `executions.wait` for a wait. Its ten fields are the call (`operation`), `outcome` (`ok`, `refused`, `error`), the run's `status`, `duration_ms`, `execution_id`, `operation_code`, `estimated`, `actual`, `error_code` and `cache_hit` — ids, money and a verdict, never a prompt or an answer. Credit movements and webhooks leave none.

```python
from slen import LoggerSpanRecorder

slen = Slen(span_recorder=LoggerSpanRecorder(logging.getLogger("billing.spans")))
```

`span_recorder` takes anything with `record(span)`: `LoggerSpanRecorder` writes one `slen.span` line per span with its fields, `slen.testing.MemorySpanRecorder` keeps them, and `slen.otel.OtelSpanRecorder` hands them to an OpenTelemetry tracer of yours (`pip install "slen[otel]"`; the export is your `opentelemetry-sdk`'s). A recorder that raises does not fail the call.

## Long-running servers

A server builds a client once per process and serves every request with it. A client keeps no state of a call, so one per process is the rule.

- **Build the client in the process that uses it**, never when a module is imported: a client made before a server forks its workers (`gunicorn --preload`) would share its connections between them. FastAPI: in the `lifespan` of the application, and `AsyncSlen` in the worker's own event loop. Django: on the first request a process serves. A client cannot be pickled or copied for the same reason: build one in each process.
- **The context of a request goes through `with_logger()`**: a copy over the same connections and span recorder. Never change the shared client.
- **Do not wait in a request handler.** `executions.wait()` keeps the handler open for as long as the run takes. Start the run with `execute_async()` and learn its end from the `execution.finished` webhook, or wait in a queue worker.
- **A run inside a request gets a budget of its own**: `timeout` and `retries` of the call, not the client's minutes.
- **`FakeTransport` and `MemorySpanRecorder` keep everything** they are given: they are for tests, never for a server.

## The async client

```python
import asyncio

from slen import AsyncSlen


async def main() -> None:
    async with AsyncSlen() as slen:
        run = await slen.operations.execute("support.reply", {"messages": []}, idempotency_key="ticket-42:reply")
        print(run.status)


asyncio.run(main())
```

`AsyncSlen` takes the same options and has the same calls, awaited; `list_all()` and `entries_all()` are not awaited, they answer an async iterator. Cancelling the task of a call ends it: the cancellation is never repeated and never swallowed. It runs on asyncio; trio is not supported.

**The clock of an attempt.** `AsyncSlen` holds each attempt — connecting, sending, the headers and the whole body — to one deadline. `Slen` runs on httpx's clocks, which count each phase, and checks the attempt's deadline between the pieces of the body: an attempt whose body stalls after its headers is a `TimeoutError` after at most about twice `timeout`.

## Request ids

Every answer of the API carries the id of its request, the one its log lines and support find it by. Every call that reads an answer gives it to you as `request_id`, read from the `X-Request-Id` header; `None` when the answer had none:

```python
customer = slen.customers.get("user_8421")

print(customer.request_id)
```

It is the last field of the answer and takes no part in `==`, but `dataclasses.asdict()` carries it; the rows of a page and what an answer holds (the accounts of a customer) have none. `executions.wait()` gives the id of its last read; `delete()` answers nothing. An error carries it as `request_id`. A dataclass that holds a `dict` (`output`, `metadata`) cannot be hashed.

**Your own id.** `request_id=` of a call sends your id as `X-Request-Id`, the same on every attempt of the call; the API keeps it, so its log lines, the `request_id` of the journal and of an error carry your id — a call that got no answer at all (`ConnectionError`, `TimeoutError`) raises with your id too, while an answer that brings another id has the last word. It is 8 to 128 of `A-Z a-z 0-9 . _ : -` (`"order-42:charge"`); anything else is an `InvalidRequestError` before the wire, since the API would replace it. One id names one request, so `list_all()`, `entries_all()` and `executions.wait()` take none: Python refuses the argument itself.

## Errors

Every failure is a `SlenError` with `code`, `status`, `details`, `request_id` (what support finds the request by — the `X-Request-Id` of the answer, else `error.request_id` of its body; with no answer, the call's own `request_id`) and `retry_after_seconds`; `str(error)` is its message. The code decides the type; a code this version has no name for falls back by status:

| Error | Codes | Fallback |
|---|---|---|
| `AuthenticationError` | `invalid_api_key`, `insufficient_scope`, `not_authenticated`, `not_a_member`, `account_suspended` | any other 401 / 403 |
| `PolicyDeniedError` | `policy_denied`, `model_not_allowed` | |
| `CustomerBlockedError` (a `PolicyDeniedError`) | `customer_blocked` | |
| `SpendRefusedError` (the family below) | `budget_exceeded`, `operation_limit_exceeded`, `concurrency_limit_exceeded`, `insufficient_credits`, `overrun_stopped`, `overrun_approval_required` | any other 402 |
| `RateLimitError` | `rate_limit_exceeded` | any other 429 |
| `IdempotencyConflictError` | `idempotency_conflict`, `idempotency_in_progress` | |
| `CustomerNotFoundError` | `customer_not_found` | |
| `ProviderError` | `provider_error`, `provider_unavailable`, `provider_timeout`, `provider_rate_limit`, `provider_not_configured`, `pool_exhausted` | any other 5xx |
| `OperationUncertainError` | `operation_uncertain` | |
| `ServiceUnavailableError` | `ledger_unavailable`, `service_unavailable` | |
| `FlowRuntimeError` | `flow_runtime_error`, `unrouted_port`, `step_limit_exceeded`, `http_request_failed`, `unknown_node`, `node_type_not_supported`, `execution_conflict` | |
| `TimeoutError` | `execution_timeout`, `background_hold_expired` | no answer in time (the SDK's own, no code) |
| `ConnectionError` | | Slen could not be reached, or the connection broke (the SDK's own, no code) |
| `InvalidResponseError` | `invalid_response`, `webhook_payload_invalid` (the SDK's own) | |
| `WebhookSignatureError` | `webhook_signature_invalid` (the SDK's own) | |
| `InvalidRequestError` | `cost_calculation_failed`; `invalid_request` (the SDK's own: refused before the wire) | everything else |

The same code is the same type in the PHP and TypeScript SDKs. Every 402 extends `SpendRefusedError`, so "money said no" is one `except` that still knows which. A 429 is not in it: `RateLimitError` is the key's own request rate. `slen.TimeoutError` and `slen.ConnectionError` also extend Python's own `TimeoutError` and `ConnectionError`, so an `except TimeoutError:` of either name catches the SDK's.

**What is retried.** No answer, a 429 and a 503 are sent again, under the same idempotency key, up to `retries` times: a `Retry-After` of up to 30 s is waited out, a longer one comes back to you as `retry_after_seconds`; otherwise the pause is 200 ms doubling, at most 5 s. A 500, 502 or 504 is never repeated — a provider may have been paid.

**Which of them may have cost money.** The money of a run is the money of the model calls its flow made. The types are drawn along that line, with one exception — the second `ProviderError` row, where the code has to be read as well:

| Error | Was money spent? | Send it again? |
|---|---|---|
| `SpendRefusedError`, `PolicyDeniedError`, `RateLimitError`, `InvalidRequestError`, `AuthenticationError`, `IdempotencyConflictError` — raised before the run began | no — nothing ran and nothing was held | only once what was refused has changed |
| `ServiceUnavailableError` | no — Slen did not carry the request out | yes, later, under the same key |
| `TimeoutError`, `ConnectionError` raised by the SDK (`code is None`) | unknown — the request may have reached the server | under the same key only: the SDK has already repeated it so, and the server runs a key once |
| `OperationUncertainError` | **unknown — it may have been.** A provider was called and its answer never came; the hold is left in place until it expires | not under a new key: under the same one the server answers with the run as it ended and runs nothing |
| `ProviderError` with a provider's code — `provider_error`, `provider_unavailable`, `provider_timeout`, `provider_rate_limit`, `provider_not_configured`, `pool_exhausted` | no — for the model call that failed: its hold was given back. A model call the run made before it was paid for (last row) | as the last row says; `provider_not_configured` needs a connection set up first |
| `ProviderError` with any other code, or with none (`code is None`) | **unknown.** A 5xx without a code this version knows lands here too — the page of a proxy that gave up, a bare 500 — and it does not say how far the run got | as for `OperationUncertainError`: not under a new key |
| `FlowRuntimeError` — and **any of the above out of `operations.execute()`** once the walk has begun: a `ProviderError`, a `SpendRefusedError` or a `PolicyDeniedError` of a later node, `ledger_unavailable`, the server's `execution_timeout` and `background_hold_expired` | whatever model calls the flow made before it stopped were paid for | a repeat under a new key pays for those again. Under the same key the server answers with the run as it ended (`replayed`) and runs nothing — fix the flow or its input, then send it under a new one |

A credit movement (`top_up`, `charge`, `adjust`) moves credits once per key: after a `TimeoutError` or a `ConnectionError`, send it again under the same key.

A success the SDK cannot read — a 2xx whose body is not the API's envelope, such as the page of a proxy, or an answer that lacks a field — is an `InvalidResponseError` with the status it came with. The call may have gone through; it is not repeated, and the body is never quoted.

## Testing your own code

```python
import httpx

from slen import Slen
from slen.testing import FakeTransport, MemorySpanRecorder

http = FakeTransport().push(200, {"data": {"status": "ok"}})
spans = MemorySpanRecorder()
slen = Slen(api_key="key-for-tests", http_client=httpx.Client(transport=http), span_recorder=spans)
```

`FakeTransport` is an httpx transport for both clients (`httpx.AsyncClient(transport=http)` for `AsyncSlen`): it answers from the queue `push()` and `push_exception()` fill and keeps every request it was given (`requests`, `last()`) — method, URL, headers and the body as JSON. A request with nothing queued is a `LookupError` that names its route. `MemorySpanRecorder` keeps the spans (`spans`, `last()`). Both are what the SDK's own suite uses.

## Development

```bash
docker run --rm -v "$PWD":/pkg -v slen-venv:/venv -w /pkg -e UV_PROJECT_ENVIRONMENT=/venv python:3.11-slim \
  sh -c 'pip install --quiet uv==0.13.6 && uv sync --locked --all-extras && uv run --no-sync pytest'
```

The suite reads `contract/` — the contract the SDKs share, copied here and not edited by hand — and runs the examples of `examples/help`. With `SLEN_OPENAPI_SPEC` naming the API's OpenAPI spec, the contract test and the help examples are held against it as well; without it those checks are skipped. `AGENTS.md` has the rules of the package.
