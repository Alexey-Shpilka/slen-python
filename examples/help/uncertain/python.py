# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start call
from slen import OperationUncertainError

email = {"messages": [{"role": "user", "content": "Write a short follow-up email."}]}
key = "order-42:email"

try:
    run = slen.operations.execute("generate_email", email, idempotency_key=key)

    print(run.status)
except OperationUncertainError as error:
    # A provider was called and its answer was lost: the call may have been paid for.
    # Keep the key. Under a new one the same request may pay for the call a second time.
    print(f"outcome unknown: {error.code}")
# docs:end

# docs:start repeat
# The same request under the same key runs nothing: it reads the execution the first one opened.
again = slen.operations.execute("generate_email", email, idempotency_key=key)

if again.status == "uncertain":
    print(f"{again.status}: {again.error_code}")
# docs:end
