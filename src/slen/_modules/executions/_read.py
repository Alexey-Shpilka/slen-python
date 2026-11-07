from slen._http._answer import Answered
from slen._http._fields import Fields
from slen._modules.executions._types import (
    AttemptCostBreakdown,
    AttemptSummary,
    ExecutionCache,
    ExecutionCost,
    ExecutionStatus,
    ExecutionStatusView,
    ExecutionTrace,
    ExecutionWarning,
    FlowExecutionEvent,
    FlowExecutionNode,
    WaitingOn,
)


def cost_of(fields: Fields) -> ExecutionCost:
    return ExecutionCost(
        estimated=fields.nullable_text("estimated"),
        actual=fields.nullable_text("actual"),
        incomplete=fields.flag("incomplete"),
    )


def cache_of(fields: Fields) -> ExecutionCache:
    return ExecutionCache(hit=fields.flag("hit"), cached_at=fields.nullable_moment("cached_at"))


def warnings_of(run: Fields) -> tuple[ExecutionWarning, ...]:
    return tuple(
        ExecutionWarning(code=row.text("code"), keys=row.optional_texts("keys"), message=row.text("message"))
        for row in run.rows("warnings")
    )


def waiting_of(fields: Fields | None) -> WaitingOn | None:
    if fields is None:
        return None

    return WaitingOn(
        node_key=fields.text("node_key"),
        type=fields.text("type"),
        resume_at=fields.nullable_moment("resume_at"),
    )


def status_view_of(answered: Answered) -> ExecutionStatusView:
    run = Fields(answered.data, "data")

    return ExecutionStatusView(
        execution_id=run.text("execution_id"),
        status=run.choice("status", ExecutionStatus),
        operation=run.text("operation"),
        output=run.nullable_json("output"),
        error_code=run.nullable_text("error_code"),
        error_message=run.nullable_text("error_message"),
        cost=cost_of(run.nested("cost")),
        cache=cache_of(run.nested("cache")),
        waiting_on=waiting_of(run.nullable_nested("waiting_on")),
        trace_url=run.text("trace_url"),
        warnings=warnings_of(run),
        retry_after_seconds=run.optional_integer("retry_after_seconds"),
        request_id=answered.request_id,
    )


def attempt_of(fields: Fields) -> AttemptSummary:
    return AttemptSummary(
        attempt_id=fields.text("attempt_id"),
        attempt_number=fields.integer("attempt_number"),
        connection_id=fields.text("connection_id"),
        pool_id=fields.optional_text("pool_id"),
        status=fields.text("status"),
        error_code=fields.optional_text("error_code"),
        latency_ms=fields.optional_integer("latency_ms"),
        cost=fields.optional_text("cost"),
        provider_request_id=fields.optional_text("provider_request_id"),
        model_code=fields.optional_text("model_code"),
        input_tokens=fields.optional_integer("input_tokens"),
        output_tokens=fields.optional_integer("output_tokens"),
        cached_input_tokens=fields.optional_integer("cached_input_tokens"),
        cache_write_tokens=fields.optional_integer("cache_write_tokens"),
        cache_write_long_tokens=fields.optional_integer("cache_write_long_tokens"),
        reasoning_tokens=fields.optional_integer("reasoning_tokens"),
        tool_calls=fields.optional_counts("tool_calls"),
        cost_breakdown=breakdown_of(fields.optional_nested("cost_breakdown")),
        cost_incomplete=fields.optional_flag("cost_incomplete"),
    )


def breakdown_of(fields: Fields | None) -> AttemptCostBreakdown | None:
    if fields is None:
        return None

    return AttemptCostBreakdown(
        input=fields.text("input"),
        cached_input=fields.text("cached_input"),
        cache_write=fields.text("cache_write"),
        output=fields.text("output"),
        tools=fields.amounts("tools"),
        total=fields.text("total"),
    )


def node_of(fields: Fields) -> FlowExecutionNode:
    return FlowExecutionNode(
        node_key=fields.text("node_key"),
        node_type=fields.text("node_type"),
        status=fields.text("status"),
        output_port=fields.optional_text("output_port"),
        cost=fields.optional_text("cost"),
        duration_ms=fields.optional_integer("duration_ms"),
        started_at=fields.moment("started_at"),
        finished_at=fields.optional_moment("finished_at"),
        metadata=fields.optional_json("metadata"),
        attempts=tuple(attempt_of(row) for row in fields.rows("attempts")),
        label=fields.optional_text("label"),
        model=fields.optional_text("model"),
        code=fields.optional_text("code"),
        output=fields.optional_json("output"),
        output_truncated=fields.optional_flag("output_truncated"),
        output_stored=fields.optional_text("output_stored"),
        estimated_cost=fields.optional_text("estimated_cost"),
        cost_status=fields.optional_text("cost_status"),
        cost_incomplete=fields.optional_flag("cost_incomplete"),
    )


def event_of(fields: Fields) -> FlowExecutionEvent:
    return FlowExecutionEvent(
        seq=fields.integer("seq"),
        type=fields.text("type"),
        node_key=fields.optional_text("node_key"),
        occurred_at=fields.moment("occurred_at"),
        payload=fields.optional_json("payload"),
    )


def trace_of(answered: Answered) -> ExecutionTrace:
    run = Fields(answered.data, "data")

    return ExecutionTrace(
        execution_id=run.text("execution_id"),
        flow_id=run.text("flow_id"),
        flow_version_id=run.text("flow_version_id"),
        flow_name=run.optional_text("flow_name"),
        operation=run.optional_text("operation"),
        operation_id=run.optional_text("operation_id"),
        status=run.choice("status", ExecutionStatus),
        error_code=run.optional_text("error_code"),
        error_message=run.optional_text("error_message"),
        cost=cost_of(run.nested("cost")),
        cache=cache_of(run.nested("cache")),
        started_at=run.moment("started_at"),
        finished_at=run.optional_moment("finished_at"),
        duration_ms=run.optional_integer("duration_ms"),
        warnings=warnings_of(run),
        nodes=tuple(node_of(row) for row in run.rows("nodes")),
        events=tuple(event_of(row) for row in run.rows("events")),
        history_paused=run.optional_flag("history_paused"),
        request_id=answered.request_id,
    )
