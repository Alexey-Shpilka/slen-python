from enum import StrEnum


# Every operation the SDK makes, as `operation` of contract/calls.json spells it: no other place spells a path.
class Endpoint(StrEnum):
    HEALTH = "GET /health"
    EXECUTE = "POST /v1/operations/execute"
    EXECUTION_STATUS = "GET /v1/executions/{id}/status"
    EXECUTION_TRACE = "GET /v1/executions/{id}"
    LIST_CUSTOMERS = "GET /v1/customers"
    GET_CUSTOMER = "GET /v1/customers/{externalUserId}"
    CREATE_CUSTOMER = "PUT /v1/customers/{externalUserId}"
    DELETE_CUSTOMER = "DELETE /v1/customers/{externalUserId}"
    UPDATE_ACCOUNT = "PUT /v1/customers/{externalUserId}/accounts/{creditType}"
    BLOCK = "POST /v1/customers/{externalUserId}/block"
    UNBLOCK = "POST /v1/customers/{externalUserId}/unblock"
    TOP_UP = "POST /v1/customers/{externalUserId}/topup"
    CHARGE = "POST /v1/customers/{externalUserId}/charge"
    ADJUST = "POST /v1/customers/{externalUserId}/adjust"
    ENTRIES = "GET /v1/customers/{externalUserId}/entries"
    PRICES = "GET /v1/credit-prices"

    @property
    def method(self) -> str:
        return self.value.partition(" ")[0]

    @property
    def route(self) -> str:
        return self.value.partition(" ")[2]
