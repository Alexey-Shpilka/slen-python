from slen._http._answer import Call
from slen._http._endpoints import Endpoint
from slen._http._request import ApiRequest, Sending
from slen._modules.executions._read import status_view_of, trace_of
from slen._modules.executions._types import ExecutionStatusView, ExecutionTrace


def status_call(execution_id: str, sending: Sending) -> Call[ExecutionStatusView]:
    request = ApiRequest(endpoint=Endpoint.EXECUTION_STATUS, params={"id": execution_id}, sending=sending)

    return Call(request, status_view_of)


def trace_call(execution_id: str, sending: Sending) -> Call[ExecutionTrace]:
    request = ApiRequest(endpoint=Endpoint.EXECUTION_TRACE, params={"id": execution_id}, sending=sending)

    return Call(request, trace_of)
