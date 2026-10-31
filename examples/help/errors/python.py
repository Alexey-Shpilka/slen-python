# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start catch
from slen import OperationUncertainError, SlenError, SpendRefusedError

email = {"messages": [{"role": "user", "content": "Write a short follow-up email."}]}


def explain(error: SlenError) -> str:
    # The spend was refused, and the code says what refused it.
    if isinstance(error, SpendRefusedError):
        return f"refused: {error.code}"

    # A provider was called and its answer was lost: the call may have been paid for.
    if isinstance(error, OperationUncertainError):
        return f"uncertain, request {error.request_id}"

    return f"{error.status} {error.code}: {error}"


try:
    run = slen.operations.execute("generate_email", email, idempotency_key="order-42:email")

    print(run.status)
except SlenError as error:
    print(explain(error))
# docs:end

# docs:start repeat
again = slen.operations.execute("generate_email", email, idempotency_key="order-42:email")

if again.is_rejected():
    print(f"rejected: {again.error_code}")
# docs:end
