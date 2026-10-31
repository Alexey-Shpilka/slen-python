from collections.abc import AsyncIterator

from slen._http._endpoints import Endpoint
from slen._http._request import ApiRequest, Sending
from slen._modules._context import AsyncContext
from slen._modules._pages import rows_of_async
from slen._modules.customers._calls import (
    AccountSettings,
    CustomerQuery,
    EntryQuery,
    Move,
    account_call,
    block_call,
    customer_call,
    delete_call,
    entries_call,
    entries_request,
    list_call,
    list_request,
    move_call,
    prices_call,
)
from slen._modules.customers._types import (
    CreditEntry,
    CreditEntryType,
    CreditPriceList,
    Customer,
    CustomerAccount,
    CustomerStatus,
)
from slen._page import Page


class AsyncCustomers:
    """The end customers of the project, for asyncio: their accounts, blocks, credit movements and statements."""

    def __init__(self, context: AsyncContext) -> None:
        self._context = context

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        search: str | None = None,
        status: CustomerStatus | None = None,
        credit_type: str | None = None,
        low_balance: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Page[Customer]:
        """One page of customers, newest first, each with every account it holds."""
        query = CustomerQuery(
            cursor=cursor,
            limit=limit,
            search=search,
            status=status,
            credit_type=credit_type,
            low_balance=low_balance,
        )

        return await self._context.transport.call(
            list_call(list_request(query, Sending(timeout=timeout, retries=retries, request_id=request_id)))
        )

    def list_all(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        search: str | None = None,
        status: CustomerStatus | None = None,
        credit_type: str | None = None,
        low_balance: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> AsyncIterator[Customer]:
        """Every customer list() reads, page after page, one request a page as the loop reaches it."""
        query = CustomerQuery(
            cursor=cursor,
            limit=limit,
            search=search,
            status=status,
            credit_type=credit_type,
            low_balance=low_balance,
        )

        return rows_of_async(list_request(query, Sending(timeout=timeout, retries=retries)), self._list_page)

    async def get(
        self,
        external_user_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Customer:
        """One customer with its accounts; one the project has never seen is CustomerNotFoundError."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(customer_call(Endpoint.GET_CUSTOMER, external_user_id, sending))

    async def create(
        self,
        external_user_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Customer:
        """Makes sure the customer exists, with no account and no credits; answers the one there is otherwise."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(customer_call(Endpoint.CREATE_CUSTOMER, external_user_id, sending))

    async def update_account(
        self,
        external_user_id: str,
        credit_type: str,
        *,
        allow_negative: bool = False,
        low_balance_threshold: str = "0",
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> CustomerAccount:
        """Sets the whole of the settings of one account, creating the customer and the account if need be."""
        settings = AccountSettings(
            external_user_id=external_user_id,
            credit_type=credit_type,
            allow_negative=allow_negative,
            low_balance_threshold=low_balance_threshold,
        )
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(account_call(settings, sending))

    async def block(
        self,
        external_user_id: str,
        *,
        reason: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Customer:
        """Blocks the customer: its new runs are refused CustomerBlockedError; its credits can still move."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(block_call(external_user_id, reason, sending))

    async def unblock(
        self,
        external_user_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Customer:
        """Lifts the block: the customer is active again."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(customer_call(Endpoint.UNBLOCK, external_user_id, sending))

    async def delete(
        self,
        external_user_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> None:
        """Deletes a customer nothing ever happened to; one with history is refused: block it instead."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(delete_call(external_user_id, sending))

    async def top_up(
        self,
        external_user_id: str,
        credits: str,
        *,
        credit_type: str = "default",
        note: str | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> CustomerAccount:
        """Adds credits, creating the customer and the account if need be; a repeated key moves nothing."""
        move = Move(
            endpoint=Endpoint.TOP_UP,
            external_user_id=external_user_id,
            credits=credits,
            credit_type=credit_type,
            note=note,
            idempotency_key=idempotency_key,
        )
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(move_call(move, sending))

    async def charge(
        self,
        external_user_id: str,
        credits: str,
        *,
        credit_type: str = "default",
        note: str | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> CustomerAccount:
        """Takes credits for a service of yours; InsufficientCreditsError when the account cannot cover them."""
        move = Move(
            endpoint=Endpoint.CHARGE,
            external_user_id=external_user_id,
            credits=credits,
            credit_type=credit_type,
            note=note,
            idempotency_key=idempotency_key,
        )
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(move_call(move, sending))

    async def adjust(
        self,
        external_user_id: str,
        credits: str,
        *,
        credit_type: str = "default",
        note: str | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> CustomerAccount:
        """Corrects the balance by a signed amount other than zero."""
        move = Move(
            endpoint=Endpoint.ADJUST,
            external_user_id=external_user_id,
            credits=credits,
            credit_type=credit_type,
            note=note,
            idempotency_key=idempotency_key,
        )
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(move_call(move, sending))

    async def entries(
        self,
        external_user_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        credit_type: str | None = None,
        entry_type: CreditEntryType | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Page[CreditEntry]:
        """One page of the customer's statement, newest first; a customer with no account has an empty one."""
        query = EntryQuery(
            external_user_id=external_user_id,
            cursor=cursor,
            limit=limit,
            credit_type=credit_type,
            entry_type=entry_type,
        )
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(entries_call(entries_request(query, sending)))

    def entries_all(
        self,
        external_user_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        credit_type: str | None = None,
        entry_type: CreditEntryType | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> AsyncIterator[CreditEntry]:
        """Every entry of the statement entries() reads, page after page, one request a page as the loop reaches it."""
        query = EntryQuery(
            external_user_id=external_user_id,
            cursor=cursor,
            limit=limit,
            credit_type=credit_type,
            entry_type=entry_type,
        )

        return rows_of_async(entries_request(query, Sending(timeout=timeout, retries=retries)), self._entries_page)

    async def prices(
        self,
        *,
        operation_code: str | None = None,
        credit_type: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> CreditPriceList:
        """The price list: how many credits one run of an operation holds from its customer."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(prices_call(operation_code, credit_type, sending))

    async def _list_page(self, request: ApiRequest) -> Page[Customer]:
        return await self._context.transport.call(list_call(request))

    async def _entries_page(self, request: ApiRequest) -> Page[CreditEntry]:
        return await self._context.transport.call(entries_call(request))
