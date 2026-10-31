import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import TypeVar

from slen._errors import INVALID_RESPONSE, InvalidResponseError
from slen._http._request import ApiRequest, refuse_before_the_wire
from slen._page import Page

T = TypeVar("T")


# Every row of a list, page after page: the arguments are checked at the call, a page is asked for when the loop
# reaches it. The first page has the cursor of the call, each next one the cursor the page before answered.
def rows_of(first: ApiRequest, fetch: Callable[[ApiRequest], Page[T]]) -> Iterator[T]:
    refuse_before_the_wire(first)

    return pages_of(first, fetch)


def pages_of(first: ApiRequest, fetch: Callable[[ApiRequest], Page[T]]) -> Iterator[T]:
    request = first

    while True:
        page = fetch(request)
        yield from page.data

        if page.next_cursor is None:
            return

        request = next_page(request, page)


def rows_of_async(first: ApiRequest, fetch: Callable[[ApiRequest], Awaitable[Page[T]]]) -> AsyncIterator[T]:
    refuse_before_the_wire(first)

    return pages_of_async(first, fetch)


async def pages_of_async(first: ApiRequest, fetch: Callable[[ApiRequest], Awaitable[Page[T]]]) -> AsyncIterator[T]:
    request = first

    while True:
        page = await fetch(request)

        for row in page.data:
            yield row

        if page.next_cursor is None:
            return

        request = next_page(request, page)


# The same cursor again would be the same page again, for ever.
def next_page(request: ApiRequest, page: Page[T]) -> ApiRequest:
    if page.next_cursor == request.query.get("cursor"):
        raise InvalidResponseError(
            f"Slen answered a page of {request.endpoint} with the cursor it was asked for; "
            "reading on would read the same page forever.",
            code=INVALID_RESPONSE,
            status=200,
            request_id=page.request_id,
        )

    return dataclasses.replace(request, query={**request.query, "cursor": page.next_cursor})
