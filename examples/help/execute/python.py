# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start send
run = slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email to Ada."}]},
    customer="user_8421",
    context={"plan": "pro"},
    idempotency_key="order-57:email",
)
# docs:end

# docs:start result
from slen import ExecutionResult


def report(run: ExecutionResult) -> None:
    if run.is_completed() and run.output is not None:
        print(run.output["content"])
        return

    if run.is_rejected():
        print(f"Refused: {run.error_code} — {run.error_message}")
        return

    if run.is_pending():
        print(f"Not over yet: {run.status}. Read it again in {run.retry_after_seconds} s.")
        return

    print(f"Did not complete: {run.status}, {run.error_code}")


report(run)
# docs:end
