# docs:start client
import logging

from slen import Slen

# Stands in for the logger of your application.
logger = logging.getLogger("billing")

# No api_key: the client reads SLEN_API_KEY.
slen = Slen(timeout=120.0, connect_timeout=3.0, retries=3, logger=logger)
# docs:end

# docs:start call
run = slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email."}]},
    idempotency_key="order-42:email",
)

print(run.status)
# docs:end
