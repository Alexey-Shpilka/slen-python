# docs:start request
import hashlib
import hmac
import time

# Stands in for the request Slen sends to your endpoint: its raw body and its
# Slen-Signature header, signed here with the secret of the example's endpoint.
secret = "whsec_example_endpoint"
payload = (
    '{"id":"74438200973594801","type":"execution.finished","created_at":"2026-10-17T12:00:00+00:00",'
    '"data":{"execution_id":"74438200973594700","flow_id":"74438200973590001","operation":"generate_email",'
    '"status":"completed","error_code":null}}'
)

timestamp = int(time.time())
mac = hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
signature = f"t={timestamp},v1={mac}"
# docs:end

# docs:start receive
from slen import CustomerBalanceLowEvent, ExecutionFinishedEvent, Webhooks

# A receiver needs the secret of the endpoint, not an API key. Pass the body as it arrived.
webhooks = Webhooks(secret=secret)
event = webhooks.construct_event(payload, signature)

if isinstance(event, ExecutionFinishedEvent):
    print(f"{event.type}: {event.data.execution_id} {event.data.status}")

if isinstance(event, CustomerBalanceLowEvent):
    print(f"{event.type}: {event.data.external_user_id}")
# docs:end

# docs:start refused
from slen import WebhookSignatureError

try:
    webhooks.construct_event(payload.replace("completed", "failed"), signature)
except WebhookSignatureError as error:
    # Not the body Slen signed: answer 400 and do nothing with it.
    print(f"refused: {error.reason}")
# docs:end
