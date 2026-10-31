# docs:start client
from slen import Slen

slen = Slen()
# docs:end

# docs:start key
from slen import idempotency_key_for_job

# The id of the job of your own queue that sends this request.
job_id = "a1f7c2e9"
key = idempotency_key_for_job(job_id, "generate_email")
# docs:end

# docs:start send
email = {"messages": [{"role": "user", "content": "Write a short follow-up email."}]}

run = slen.operations.execute("generate_email", email, idempotency_key=key)

print(run.status)
# docs:end

# docs:start repeat
# The queue runs the same job again, so the key is the same.
again = slen.operations.execute("generate_email", email, idempotency_key=key)

if again.replayed:
    print(f"Execution {again.execution_id} ran once. This answer is a replay.")
# docs:end

# docs:start conflict
from slen import IdempotencyConflictError

try:
    slen.operations.execute(
        "generate_email",
        {"messages": [{"role": "user", "content": "Write a short thank-you email."}]},
        idempotency_key=key,
    )
except IdempotencyConflictError as error:
    print(f"Refused: {error.code}")
# docs:end
