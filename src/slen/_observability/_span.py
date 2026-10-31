from dataclasses import dataclass, fields
from typing import Final

from slen._modules.executions._types import ExecutionStatus

# The names a span is written under; a call that is not here writes no span.
SPAN_OPERATIONS: Final = ("operations.execute", "operations.execute_async", "executions.wait")


@dataclass(frozen=True, slots=True, kw_only=True)
class SlenSpan:
    """One run as an APM sees it: money, ids, a verdict and a duration — never a prompt or an output."""

    operation: str
    outcome: str
    status: ExecutionStatus | None
    duration_ms: int
    execution_id: str | None
    operation_code: str | None
    estimated: str | None
    actual: str | None
    error_code: str | None
    cache_hit: bool | None


# The span as flat attributes, in the order of the contract, without the fields that are None; false is kept.
def attributes_of(span: SlenSpan) -> dict[str, str | int | bool]:
    attributes: dict[str, str | int | bool] = {}

    for described in fields(span):
        value: object = getattr(span, described.name)

        if isinstance(value, str | int | bool):
            attributes[described.name] = str(value) if isinstance(value, ExecutionStatus) else value

    return attributes
