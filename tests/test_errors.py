import builtins
import inspect
import json
import pickle
import re
from typing import Any, Final

import pytest

import slen
from slen import SlenError, WebhookSignatureError
from slen._http._answer import HttpAnswer
from slen._http._error_map import BY_CODE, error_from_answer
from slen.testing import FakeTransport
from support.harness import Kind, raised
from support.paths import CONTRACT, ROOT

CONTRACT_ERRORS: Final[dict[str, Any]] = json.loads((CONTRACT / "error-codes.json").read_text(encoding="utf-8"))
TYPES: Final[dict[str, Any]] = CONTRACT_ERRORS["types"]
CODES: Final[dict[str, Any]] = CONTRACT_ERRORS["codes"]


def class_of(contract_type: str) -> type[SlenError]:
    found: type[SlenError] = getattr(slen, f"{contract_type}Error")

    return found


def error_classes() -> dict[str, type[SlenError]]:
    return {
        name: value
        for name, value in vars(slen).items()
        if inspect.isclass(value) and issubclass(value, SlenError) and name in slen.__all__
    }


def answer(status: int, body: object) -> HttpAnswer:
    return HttpAnswer(status=status, body=body, body_length=1, request_id=None, retry_after=None)


@pytest.mark.parametrize(("name", "described"), list(TYPES.items()))
def test_every_type_of_the_contract_is_a_class_with_its_parent(name: str, described: dict[str, str]) -> None:
    assert class_of(described["extends"]) in class_of(name).__bases__


def test_every_error_class_is_a_type_of_the_contract() -> None:
    names = {f"{name}Error" for name in TYPES} | {"SlenError"}

    assert set(error_classes()) == names
    assert len(names) == 23


def test_timeout_and_connection_errors_extend_the_builtins_too() -> None:
    assert issubclass(slen.TimeoutError, builtins.TimeoutError)
    assert issubclass(slen.ConnectionError, builtins.ConnectionError)
    assert str(slen.TimeoutError("no answer")) == "no answer"
    assert slen.TimeoutError("no answer").errno is None


def test_the_table_of_codes_is_the_contracts_both_ways() -> None:
    assert {code: kind.__name__ for code, kind in BY_CODE.items()} == {
        code: f"{line['type']}Error" for code, line in CODES.items()
    }


@pytest.mark.parametrize(("code", "line"), list(CODES.items()))
def test_a_code_becomes_its_type_whatever_the_status(code: str, line: dict[str, Any]) -> None:
    for status in (line["status"], 400, 503):
        error = error_from_answer(answer(status, {"error": {"code": code, "message": "m"}}), 0.0)

        assert type(error) is class_of(line["type"])
        assert error.code == code


@pytest.mark.parametrize(
    ("status", "contract_type"),
    [
        *((int(status), name) for status, name in CONTRACT_ERRORS["fallback"]["by_status"].items()),
        (500, CONTRACT_ERRORS["fallback"]["server_error"]),
        (502, CONTRACT_ERRORS["fallback"]["server_error"]),
        (404, CONTRACT_ERRORS["fallback"]["otherwise"]),
        (422, CONTRACT_ERRORS["fallback"]["otherwise"]),
    ],
)
def test_a_code_outside_the_table_falls_back_by_status(status: int, contract_type: str) -> None:
    for body in ({"error": {"code": "a_code_from_the_future"}}, {}, None):
        assert type(error_from_answer(answer(status, body), 0.0)) is class_of(contract_type)


def test_an_error_reads_message_details_and_request_id_of_the_envelope() -> None:
    body = {"error": {"code": "budget_exceeded", "message": "Spent", "details": {"budget_id": "7"}, "request_id": "r1"}}
    error = error_from_answer(answer(402, body), 0.0)

    assert str(error) == "Spent"
    assert dict(error.details) == {"budget_id": "7"}
    assert error.request_id == "r1"
    assert error.status == 402


def test_a_field_validation_is_read_as_details() -> None:
    body = {"message": "The model field is required.", "errors": {"model": ["The model field is required."]}}
    error = error_from_answer(answer(422, body), 0.0)

    assert isinstance(error, slen.InvalidRequestError)
    assert str(error) == "The model field is required."
    assert dict(error.details) == {"errors": {"model": ["The model field is required."]}}


@pytest.mark.parametrize(("code", "local"), list(CONTRACT_ERRORS["local"].items()))
def test_the_local_codes_are_raised_in_their_types(code: str, local: dict[str, Any]) -> None:
    assert "python" in local["sdks"]
    assert class_of(local["type"]).__name__ in slen.__all__


def test_a_refusal_before_the_wire_is_an_invalid_request(kind: Kind) -> None:
    fake = FakeTransport()

    error = raised(kind, fake, lambda client: client.customers.top_up("user 42", "0"))

    assert isinstance(error, slen.InvalidRequestError)
    assert error.code == "invalid_request"
    assert fake.requests == ()


@pytest.mark.parametrize("kind_of_error", sorted(error_classes()))
def test_an_error_survives_a_trip_through_pickle(kind_of_error: str) -> None:
    kind = error_classes()[kind_of_error]
    options: dict[str, Any] = {"reason": "outside_tolerance"} if kind is WebhookSignatureError else {}
    error = kind(
        "message", code="a_code", status=409, details={"a": 1}, request_id="r1", retry_after_seconds=2, **options
    )

    copied = pickle.loads(pickle.dumps(error))  # noqa: S301 - our own bytes

    assert type(copied) is kind
    assert (str(copied), copied.code, copied.status, dict(copied.details)) == ("message", "a_code", 409, {"a": 1})
    assert (copied.request_id, copied.retry_after_seconds) == ("r1", 2)
    assert getattr(copied, "reason", None) == options.get("reason")


def test_an_error_has_its_attributes_and_none_of_a_value_it_was_not_given() -> None:
    error = SlenError("plain")

    assert (error.code, error.status, dict(error.details), error.request_id, error.retry_after_seconds) == (
        None,
        None,
        {},
        None,
        None,
    )


# ---------------------------------------------------------------------------
# The tables of the README are the contract's.

README = (ROOT / "README.md").read_text(encoding="utf-8")


def readme_rows(header: str) -> list[list[str]]:
    table = README.split(header, 1)[1].split("\n\n", 1)[0]

    return [[cell.strip() for cell in line.strip("|").split("|")] for line in table.splitlines()[2:]]


def test_the_table_of_errors_of_the_readme_is_the_contracts() -> None:
    listed: dict[str, set[str]] = {}

    for kind, codes, _ in readme_rows("| Error | Codes | Fallback |"):
        name = kind.split("`")[1]
        listed[name] = set(re.findall(r"`([a-z_]+)`", codes))

    wanted: dict[str, set[str]] = {}

    for code, line in CODES.items():
        wanted.setdefault(f"{line['type']}Error", set()).add(code)

    for code, local in CONTRACT_ERRORS["local"].items():
        wanted.setdefault(f"{local['type']}Error", set()).add(code)

    family = {f"{name}Error" for name, line in TYPES.items() if line["extends"] == "SpendRefused"}
    folded = {name: codes for name, codes in wanted.items() if name not in family}
    folded["SpendRefusedError"] = set().union(*(wanted.get(name, set()) for name in family))

    assert {name: codes for name, codes in listed.items() if codes} == folded


def test_the_money_table_of_the_readme_names_every_type() -> None:
    named = {
        name
        for row in readme_rows("| Error | Was money spent? | Send it again? |")
        for name in re.findall(r"`([A-Za-z]+Error)`", row[0])
    }

    assert named == {
        "SpendRefusedError",
        "PolicyDeniedError",
        "RateLimitError",
        "InvalidRequestError",
        "AuthenticationError",
        "IdempotencyConflictError",
        "ServiceUnavailableError",
        "TimeoutError",
        "ConnectionError",
        "OperationUncertainError",
        "ProviderError",
        "FlowRuntimeError",
    }
