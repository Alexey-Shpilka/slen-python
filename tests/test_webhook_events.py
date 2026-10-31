import dataclasses
from typing import Any, Final

import pytest

from slen import (
    ApprovalDecidedEventData,
    ApprovalRequestedEventData,
    CustomerBalanceLowEventData,
    ExecutionFinishedEventData,
    WebhookEvent,
    WebhookEventType,
)
from slen._modules.webhooks._events import TYPED
from support.spec import resolved, schema, spec

# The events of a webhook against `webhooks:` of the spec: the names, the envelope, the data of each typed one.

TYPED_DATA: Final[dict[str, type]] = {
    "execution.finished": ExecutionFinishedEventData,
    "customer.balance_low": CustomerBalanceLowEventData,
    "approval.requested": ApprovalRequestedEventData,
    "approval.decided": ApprovalDecidedEventData,
}


def body_of(name: str) -> dict[str, Any]:
    delivery = spec()["webhooks"][name]["post"]["requestBody"]["content"]["application/json"]["schema"]

    return resolved(delivery)


def test_the_names_of_the_events_are_the_specs_both_ways() -> None:
    names = {str(member) for member in WebhookEventType}

    assert names == set(spec()["webhooks"])
    assert names == set(schema("WebhookEventType")["enum"])


def test_the_envelope_is_the_specs() -> None:
    envelope = schema("WebhookEnvelope")

    assert {field.name for field in dataclasses.fields(WebhookEvent)} | {"data"} == set(envelope["properties"])
    assert set(envelope["required"]) == {"id", "type", "created_at", "data"}


def test_the_sdk_types_the_data_of_four_events() -> None:
    assert set(TYPED) == set(TYPED_DATA)


@pytest.mark.parametrize(("name", "kind"), list(TYPED_DATA.items()))
def test_the_data_of_a_typed_event_is_the_specs_field_for_field(name: str, kind: type) -> None:
    data = resolved(body_of(name)["properties"]["data"])
    fields = {field.name for field in dataclasses.fields(kind)}

    assert fields == set(data["properties"])
    assert fields == set(data["required"])
