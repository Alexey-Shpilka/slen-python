import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, TypeAlias, cast

from slen._errors import refused
from slen._http._endpoints import Endpoint

# What the API keeps of a caller's X-Request-Id; anything else it silently replaces with a UUID.
REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._:-]{8,128}")
PLACEHOLDER: Final = re.compile(r"\{([^}]+)\}")

Envelope: TypeAlias = Literal["data", "page", "list", "body"]
QueryValue: TypeAlias = str | int | bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Sending:
    timeout: float | None = None
    retries: int | None = None
    request_id: str | None = None


NOT_SAID: Final = Sending()


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiRequest:
    endpoint: Endpoint
    params: Mapping[str, str] = field(default_factory=dict[str, str])
    query: Mapping[str, QueryValue] = field(default_factory=dict[str, QueryValue])
    body: bytes | None = None
    idempotency_key: str | None = None
    sending: Sending = NOT_SAID
    envelope: Envelope = "data"
    wants_body: bool = True
    done_after_no_answer: str | None = None


def placeholders(route: str) -> list[str]:
    return PLACEHOLDER.findall(route)


def refuse_before_the_wire(request: ApiRequest) -> None:
    refuse_sending(request.sending, request.endpoint)

    for name in placeholders(request.endpoint.route):
        value = request.params.get(name)

        if not isinstance(value, str) or not value.strip():
            raise refused(f"Slen: {request.endpoint} needs a {name} that is not empty.")

    key: object = request.idempotency_key

    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise refused(
            f"Slen: the idempotency key of {request.endpoint} is empty; "
            "pass one that is not, or none to have one generated."
        )


def refuse_sending(sending: Sending, endpoint: Endpoint) -> None:
    timeout: object = sending.timeout
    retries: object = sending.retries
    request_id: object = sending.request_id

    # Negated on purpose: NaN is not above 0 either.
    if timeout is not None and not (isinstance(timeout, int | float) and not isinstance(timeout, bool) and timeout > 0):
        raise refused(f"Slen: timeout must be a number above 0, got {timeout!r}.")

    if retries is not None and not (isinstance(retries, int) and not isinstance(retries, bool) and retries >= 0):
        raise refused(f"Slen: retries must be an integer of at least 0, got {retries!r}.")

    if request_id is not None and not (isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id)):
        raise refused(f'Slen: the request id of {endpoint} must be 8 to 128 of A-Z, a-z, 0-9, ".", "_", ":" and "-".')


def encode_body(endpoint: Endpoint, body: Mapping[str, object]) -> bytes:
    # The bytes are the SDK's own, whatever httpx does with `json=`: the server hashes them under the key.
    try:
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=plain).encode()
    except (TypeError, ValueError) as error:
        raise refused(f"Slen: the body of {endpoint} is not JSON: {error}") from None


def plain(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(cast("Mapping[str, object]", value))

    raise TypeError(f"an object of type {type(value).__name__} is not JSON")
