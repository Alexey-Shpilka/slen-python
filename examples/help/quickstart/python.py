# docs:start client
from slen import Slen

# The key is read from SLEN_API_KEY.
slen = Slen()
# docs:end

# docs:start send
run = slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email."}]},
    idempotency_key="order-42:email",
)
# docs:end

# docs:start result
if run.is_completed() and run.output is not None:
    print(run.output["content"])
# docs:end
