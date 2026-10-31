import json
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from slen import InvalidResponseError, Slen, UnknownWebhookEvent, WebhookEvent, Webhooks, WebhookSignatureError
from support.harness import RecordingLogger
from support.paths import CONTRACT

# The vectors are signed by the backend's own webhook signer; both other SDKs read the same file.
VECTORS: Final[dict[str, Any]] = json.loads((CONTRACT / "webhook-vectors.json").read_text(encoding="utf-8"))
CASES: Final[list[dict[str, Any]]] = VECTORS["cases"]


def moment(case: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(case["now"], tz=UTC)


def webhooks() -> Webhooks:
    return Webhooks(secret=VECTORS["secret"], tolerance_seconds=VECTORS["tolerance_seconds"])


def test_there_are_thirty_nine_vectors() -> None:
    assert len(CASES) == 39
    assert VECTORS["header_name"] == "Slen-Signature"


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_verify_answers_each_vector(case: dict[str, Any]) -> None:
    for payload in (case["payload"], case["payload"].encode()):
        assert webhooks().verify(payload, case["header"], now=moment(case)) is case["valid"]


@pytest.mark.parametrize("case", [case for case in CASES if not case["valid"]], ids=lambda case: case["name"])
def test_construct_event_refuses_a_signature_that_does_not_hold(case: dict[str, Any]) -> None:
    with pytest.raises(WebhookSignatureError) as refused:
        webhooks().construct_event(case["payload"], case["header"], now=moment(case))

    assert (refused.value.reason, refused.value.code) == (case["reason"], "webhook_signature_invalid")


@pytest.mark.parametrize(
    "case", [case for case in CASES if case["valid"] and case["event"] is None], ids=lambda case: case["name"]
)
def test_construct_event_refuses_a_signed_body_that_is_not_an_event(case: dict[str, Any]) -> None:
    with pytest.raises(InvalidResponseError) as unreadable:
        webhooks().construct_event(case["payload"], case["header"], now=moment(case))

    assert unreadable.value.code == "webhook_payload_invalid"


@pytest.mark.parametrize("case", [case for case in CASES if case["event"] is not None], ids=lambda case: case["name"])
def test_construct_event_reads_the_event_of_a_valid_vector(case: dict[str, Any]) -> None:
    event: WebhookEvent = webhooks().construct_event(case["payload"], case["header"], now=moment(case))

    assert case["event"] == {"id": event.id, "type": event.type}
    assert event.created_at.utcoffset() is not None


def test_an_event_of_a_type_the_sdk_does_not_type_keeps_its_data() -> None:
    case = next(case for case in CASES if case["name"].startswith("flow.published"))

    event = webhooks().construct_event(case["payload"], case["header"], now=moment(case))

    assert isinstance(event, UnknownWebhookEvent)
    assert event.data == {"flow_id": "74438200973590001", "version": 7}


def test_the_secret_of_the_call_wins_and_none_at_all_is_a_value_error() -> None:
    case = CASES[0]

    assert Webhooks().verify(case["payload"], case["header"], secret=VECTORS["secret"], now=moment(case))
    assert not Webhooks(secret="whsec_other").verify(case["payload"], case["header"], now=moment(case))

    with pytest.raises(ValueError, match="signing secret"):
        Webhooks().verify(case["payload"], case["header"])

    with pytest.raises(ValueError, match="signing secret"):
        webhooks().verify(case["payload"], case["header"], secret="  ")


def test_the_tolerance_of_the_call_wins() -> None:
    case = CASES[0]
    later = datetime.fromtimestamp(case["now"] + 600, tz=UTC)

    assert not webhooks().verify(case["payload"], case["header"], now=later)
    assert webhooks().verify(case["payload"], case["header"], now=later, tolerance_seconds=601)


@pytest.mark.parametrize("tolerance", [0, -1])
def test_a_tolerance_below_one_second_is_a_value_error(tolerance: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Webhooks(secret="s", tolerance_seconds=tolerance)


def test_a_time_without_its_zone_and_a_body_of_another_type_are_refused() -> None:
    case = CASES[0]

    with pytest.raises(ValueError, match="time zone"):
        webhooks().verify(case["payload"], case["header"], now=datetime(2026, 10, 17))

    with pytest.raises(TypeError):
        webhooks().verify(json.loads(case["payload"]), case["header"])


def test_a_refusal_is_written_once_without_the_body_the_header_or_the_secret() -> None:
    logger = RecordingLogger()
    case = next(case for case in CASES if case["reason"] == "outside_tolerance")

    Webhooks(secret=VECTORS["secret"], logger=logger).verify(case["payload"], case["header"], now=moment(case))

    assert [(entry.event, entry.level) for entry in logger.entries] == [("slen.webhook.rejected", "warning")]
    assert logger.entries[0].fields == {"reason": "outside_tolerance", "age_seconds": case["now"] - 1792238400}
    written = str(logger.entries[0].fields)
    assert VECTORS["secret"] not in written
    assert case["header"] not in written


def test_a_client_checks_with_its_own_secret_and_tolerance() -> None:
    case = CASES[0]
    client = Slen(api_key="key-for-tests", webhook_secret=VECTORS["secret"], webhook_tolerance_seconds=300)

    assert client.webhooks.verify(case["payload"], case["header"], now=moment(case))
