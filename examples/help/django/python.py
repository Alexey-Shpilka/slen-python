# docs:start client
import functools
import logging
from collections.abc import MutableMapping
from typing import Any

from django.http import HttpRequest, JsonResponse

from slen import Slen


# One client per worker process, built by the first request the process serves — never when the module is
# imported or the app is ready, so workers forked after loading the application share no connections.
@functools.cache
def shared_slen() -> Slen:
    return Slen()


# Keeps the fields of each event of the SDK and adds the id of the request being served.
class RequestLog(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        return msg, {**kwargs, "extra": {**(kwargs.get("extra") or {}), **(self.extra or {})}}


def slen_of(request: HttpRequest) -> Slen:
    # A copy of the process's client that logs with this request's id; the shared client does not change.
    log = RequestLog(logging.getLogger("orders"), {"http_request_id": request.headers.get("X-Request-Id", "")})

    return shared_slen().with_logger(log)
# docs:end


# docs:start submit
def email_the_order(request: HttpRequest, order_id: int) -> JsonResponse:
    # The run goes to a worker and the request is answered at once: a view does not wait for a run.
    run = slen_of(request).operations.execute_async(
        "generate_email",
        {"messages": [{"role": "user", "content": f"Write a short email: order {order_id} has shipped."}]},
        idempotency_key=f"order-{order_id}:email",
    )

    return JsonResponse({"execution_id": run.execution_id, "status": run.status}, status=202)
# docs:end


# docs:start status
def run_status(request: HttpRequest, execution_id: str) -> JsonResponse:
    # One read of the run; its end arrives as the execution.finished webhook.
    run = slen_of(request).executions.get(execution_id)

    return JsonResponse({"execution_id": run.execution_id, "status": run.status})
# docs:end


# docs:start urls
from django.urls import path
from django.views.decorators.http import require_GET, require_POST

urlpatterns = [
    path("orders/<int:order_id>/email", require_POST(email_the_order)),
    path("runs/<str:execution_id>", require_GET(run_status)),
]
# docs:end
