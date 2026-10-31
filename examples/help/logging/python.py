# docs:start logger
import logging


# Stands in for a handler of your application: it prints each event with the route and, for an answer, its status.
class Printer(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        fields = vars(record)
        line = f"{record.levelname.lower()} {record.getMessage()} {fields['method']} {fields['route']}"

        if "status" in fields:
            line += f" {fields['status']}"

        print(line)


logger = logging.getLogger("billing")
logger.setLevel(logging.DEBUG)
logger.addHandler(Printer())
# docs:end

# docs:start client
from slen import Slen

slen = Slen(logger=logger)
# docs:end

# docs:start send
slen.operations.execute(
    "generate_email",
    {"messages": [{"role": "user", "content": "Write a short follow-up email."}]},
    idempotency_key="order-77:email",
)
# docs:end
