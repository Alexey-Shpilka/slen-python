# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start submit
queued = slen.operations.execute_async(
    "summarize_report",
    {"messages": [{"role": "user", "content": "Summarize the third-quarter report."}]},
    idempotency_key="report-2026-q3:summary",
)

print(queued.status)
# docs:end

# docs:start wait
from slen import SlenError


def told(error: SlenError, failures_in_a_row: int) -> None:
    print(f"Status read failed ({failures_in_a_row} in a row): {error}")


# In a queue job or a script, not in an HTTP handler: the wait keeps the handler open.
finished = slen.executions.wait(queued.execution_id, timeout_seconds=60, on_poll_error=told)
# docs:end

# docs:start result
from slen import ExecutionStatusView


def report(run: ExecutionStatusView) -> None:
    if run.is_completed() and run.output is not None:
        print(run.output["content"])
        return

    if run.is_pending():
        print(f"Not over yet: {run.status}")
        return

    print(f"Ended as {run.status}: {run.error_code}")


report(finished)
# docs:end
