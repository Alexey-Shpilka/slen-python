from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, TypeAlias

from slen._errors import refused
from slen._http._answer import Call
from slen._http._endpoints import Endpoint
from slen._http._request import ApiRequest, Sending, encode_body
from slen._idempotency import generate_idempotency_key
from slen._modules.operations._read import result_of
from slen._modules.operations._types import ExecutionResult
from slen._observability._scope import SpanSubject

ContextValue: TypeAlias = str | int | float | bool | None

# The options that are a value of the context, and the key of the context each is.
CLAIMS: Final = MappingProxyType({"customer": "user_id", "credit_type": "credit_type"})


@dataclass(frozen=True, slots=True, kw_only=True)
class RunOrder:
    operation: str
    input: Mapping[str, Any]
    queued: bool
    customer: str | None
    credit_type: str | None
    context: Mapping[str, ContextValue] | None
    idempotency_key: str | None
    sending: Sending


def run_call(order: RunOrder) -> Call[ExecutionResult]:
    request = ApiRequest(
        endpoint=Endpoint.EXECUTE,
        body=encode_body(Endpoint.EXECUTE, body_of(order)),
        idempotency_key=generate_idempotency_key() if order.idempotency_key is None else order.idempotency_key,
        sending=order.sending,
    )

    return Call(request, result_of)


# Named by the call, not by the answer: a replayed key answers with the run as it is now.
def span_subject(order: RunOrder) -> SpanSubject:
    name = "operations.execute_async" if order.queued else "operations.execute"

    return SpanSubject(operation=name, operation_code=order.operation)


def body_of(order: RunOrder) -> dict[str, object]:
    context: dict[str, ContextValue] = dict(order.context or {})
    claim(context, "customer", order.customer)
    claim(context, "credit_type", order.credit_type)
    body: dict[str, object] = {"operation": order.operation, "input": dict(order.input)}
    body.update({"context": context} if context or order.context is not None else {})
    body.update({"execution_mode": "async"} if order.queued else {})

    return body


def claim(context: dict[str, ContextValue], option: str, value: str | None) -> None:
    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        raise refused(f"Slen: `{option}` of {Endpoint.EXECUTE} is empty; pass one that is not, or none.")

    key = CLAIMS[option]

    if key in context and (context[key] is None or text_of(context[key]) != value):
        raise refused(f"Slen: `{option}` and `context.{key}` name two different values; pass one of them.")

    context[key] = value


# A value of the context as the wire reads it: 42 and "42" name one customer.
def text_of(value: ContextValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)
