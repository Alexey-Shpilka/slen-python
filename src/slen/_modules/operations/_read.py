from slen._http._answer import Answered
from slen._http._fields import Fields
from slen._modules.executions._read import cache_of, cost_of, waiting_of
from slen._modules.executions._types import ExecutionError, ExecutionStatus
from slen._modules.operations._types import ExecutionResult


def error_of(fields: Fields | None) -> ExecutionError | None:
    if fields is None:
        return None

    return ExecutionError(code=fields.text("code"), message=fields.text("message"))


def result_of(answered: Answered) -> ExecutionResult:
    run = Fields(answered.data, "data")

    return ExecutionResult(
        execution_id=run.text("execution_id"),
        status=run.choice("status", ExecutionStatus),
        operation=run.text("operation"),
        output=run.nullable_json("output"),
        error=error_of(run.nullable_nested("error")),
        error_code=run.nullable_text("error_code"),
        error_message=run.nullable_text("error_message"),
        cost=cost_of(run.nested("cost")),
        cache=cache_of(run.nested("cache")),
        replayed=run.flag("replayed"),
        waiting_on=waiting_of(run.nullable_nested("waiting_on")),
        trace_url=run.text("trace_url"),
        retry_after_seconds=run.optional_integer("retry_after_seconds"),
        request_id=answered.request_id,
    )
