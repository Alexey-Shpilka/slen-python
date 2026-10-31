from typing import Final

from slen._errors import SlenError, contract_type_of
from slen._http._answer import HttpAnswer
from slen._http._request import ApiRequest
from slen._http._retry import RetryPause
from slen._logger import SlenLogger, write_log

# A 403 under these codes is a key that cannot do this: a setting to fix, not a refusal.
KEY_CODES: Final = frozenset({"insufficient_scope", "invalid_api_key", "not_a_member"})


# The journal of the HTTP chain. A request is written by its route template, never the values in it.
class HttpJournal:
    __slots__ = ("_logger",)

    def __init__(self, logger: SlenLogger) -> None:
        self._logger = logger

    def request(self, request: ApiRequest, attempt: int) -> None:
        write_log(self._logger, "slen.request", {**where(request), "attempt": attempt})

    def response(self, request: ApiRequest, answer: HttpAnswer, duration_ms: int) -> None:
        fields = {"status": answer.status, "duration_ms": duration_ms, "request_id": answer.request_id}
        write_log(self._logger, "slen.response", {**where(request), **fields})

    def retry(self, request: ApiRequest, attempt: int, pause: RetryPause) -> None:
        fields = {"attempt": attempt, "delay_ms": pause.delay_ms, "reason": pause.reason, "status": pause.status}
        write_log(self._logger, "slen.retry", {**where(request), **fields})

    def rejected(self, request: ApiRequest, error: SlenError, attempts: int) -> None:
        fields = {**where(request), "status": error.status, "error_code": error.code, "request_id": error.request_id}
        status = error.status or 0

        if status == 401 or (status == 403 and (error.code is None or error.code in KEY_CODES)):
            write_log(self._logger, "slen.unauthorized", fields)
            return

        if 400 <= status < 500:
            write_log(self._logger, "slen.refused", fields)
            return

        write_log(self._logger, "slen.failed", {**fields, "error_type": contract_type_of(error), "attempts": attempts})


def where(request: ApiRequest) -> dict[str, object]:
    return {"method": request.endpoint.method, "route": request.endpoint.route}
