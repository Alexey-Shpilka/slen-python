from slen._logger import SlenLogger, write_log
from slen._modules.executions._types import ExecutionWarning


# What a run said about its request, by code and keys; never the message, the journal carries no text of the server.
def log_warnings(logger: SlenLogger, execution_id: str, warnings: tuple[ExecutionWarning, ...]) -> None:
    if not warnings:
        return

    said = [{"code": one.code, "keys": None if one.keys is None else list(one.keys)} for one in warnings]
    write_log(logger, "slen.execution.warnings", {"execution_id": execution_id, "warnings": said})
