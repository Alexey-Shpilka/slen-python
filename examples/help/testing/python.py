# docs:start double
from slen.testing import FakeTransport

answer = {
    "execution_id": "74438200973594700",
    "status": "completed",
    "operation": "generate_email",
    "output": {"content": "Hi Ada, just checking in on the proposal I sent last week."},
    "error": None,
    "error_code": None,
    "error_message": None,
    "cost": {"estimated": "0.00412500", "actual": None},
    "cache": {"hit": False, "cached_at": None},
    "replayed": False,
    "waiting_on": None,
    "trace_url": "/v1/executions/74438200973594700",
}

http = FakeTransport().push(200, {"data": answer})
# docs:end

# docs:start client
import httpx

from slen import Slen

slen = Slen(api_key="key-for-tests", http_client=httpx.Client(transport=http))
# docs:end

# docs:start call
run = slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email."}]},
    idempotency_key="order-42:email",
)
# docs:end

# docs:start inspect
sent = http.last()

print(run.status)
print(sent.method, sent.url)
print(sent.headers["idempotency-key"])
print(sent.body["operation"])
# docs:end

# Harness: what the example's own double recorded, for the test that runs this
# file. Not part of any region.
recorded = http.requests
