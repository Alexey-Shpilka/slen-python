# docs:start client
import logging
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from slen import AsyncSlen


# One client per worker process, built in the worker's own event loop when it starts and closed when it stops —
# never when the module is imported, so workers forked from one process share no connections.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with AsyncSlen() as slen:
        app.state.slen = slen
        yield


app = FastAPI(lifespan=lifespan)


# Keeps the fields of each event of the SDK and adds the id of the request being served.
class RequestLog(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        return msg, {**kwargs, "extra": {**(kwargs.get("extra") or {}), **(self.extra or {})}}


def slen_of(request: Request) -> AsyncSlen:
    # A copy of the worker's client that logs with this request's id; the shared client does not change.
    shared: AsyncSlen = request.app.state.slen
    log = RequestLog(logging.getLogger("orders"), {"http_request_id": request.headers.get("x-request-id", "")})

    return shared.with_logger(log)
# docs:end


# docs:start submit
@app.post("/orders/{order_id}/email", status_code=202)
async def email_the_order(order_id: int, request: Request) -> dict[str, str]:
    # The run goes to a worker and the request is answered at once: a handler does not wait for a run.
    run = await slen_of(request).operations.execute_async(
        "generate_email",
        {"messages": [{"role": "user", "content": f"Write a short email: order {order_id} has shipped."}]},
        idempotency_key=f"order-{order_id}:email",
    )

    return {"execution_id": run.execution_id, "status": run.status}
# docs:end


# docs:start status
@app.get("/runs/{execution_id}")
async def run_status(execution_id: str, request: Request) -> dict[str, str]:
    # One read of the run; its end arrives as the execution.finished webhook.
    run = await slen_of(request).executions.get(execution_id)

    return {"execution_id": run.execution_id, "status": run.status}
# docs:end
