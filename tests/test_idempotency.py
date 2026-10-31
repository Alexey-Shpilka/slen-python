import uuid

import pytest

from slen import generate_idempotency_key, idempotency_key_for_job
from slen.testing import FakeTransport
from support.harness import Kind, data, drive, run_result


def test_a_generated_key_is_a_uuid_of_version_4_and_never_the_same() -> None:
    keys = {generate_idempotency_key() for _ in range(1000)}

    assert len(keys) == 1000
    assert {uuid.UUID(key).version for key in keys} == {4}


def test_the_key_of_a_job_names_the_job_and_the_operation() -> None:
    assert idempotency_key_for_job("a1f7c2e9", "generate_email") == "job:a1f7c2e9:generate_email"
    assert idempotency_key_for_job(42, "generate_email") == "job:42:generate_email"


@pytest.mark.parametrize(("job", "operation"), [("", "op"), ("job", " "), ("  ", "op")])
def test_the_key_of_a_job_needs_both_parts(job: str, operation: str) -> None:
    with pytest.raises(ValueError, match="needs the id of the job"):
        idempotency_key_for_job(job, operation)


@pytest.mark.parametrize(("job", "operation"), [(True, "op"), (1.5, "op"), ("job", 7)])
def test_the_key_of_a_job_takes_a_string_or_an_integer(job: object, operation: object) -> None:
    with pytest.raises(TypeError):
        idempotency_key_for_job(job, operation)  # type: ignore[arg-type]


def test_the_sdks_own_headers_win_over_the_clients_but_user_agent_is_yours(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))
    headers = {"Authorization": "Bearer stolen", "Idempotency-Key": "theirs", "User-Agent": "billing/7", "X-Team": "a"}

    drive(kind, fake, lambda slen: slen.operations.execute("op", {}, idempotency_key="ours-1"), headers=headers)
    sent = fake.last().headers

    assert sent["authorization"] == "Bearer key-for-tests"
    assert sent["idempotency-key"] == "ours-1"
    assert sent["user-agent"] == "billing/7"
    assert sent["x-team"] == "a"
    assert sent["content-type"] == "application/json"
