# docs:start recorder
import logging

from slen import LoggerSpanRecorder


# Stands in for a handler of your application: it prints the fields this page talks about.
class Printer(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        span = vars(record)
        print(
            f"{record.getMessage()}: {span['operation']} {span['outcome']} {span['status']} "
            f"{span['operation_code']} {span['execution_id']} {span['estimated']}"
        )


logger = logging.getLogger("billing.spans")
logger.setLevel(logging.INFO)
logger.addHandler(Printer())

recorder = LoggerSpanRecorder(logger)
# docs:end

# docs:start client
from slen import Slen

slen = Slen(span_recorder=recorder)
# docs:end

# docs:start send
slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email to Ada."}]},
    idempotency_key="order-61:email",
)
# docs:end
