import inspect
from collections.abc import Callable
from typing import Any, Final

import pytest

from slen import (
    AsyncCustomers,
    AsyncExecutions,
    AsyncOperations,
    AsyncSlen,
    Customers,
    Executions,
    Operations,
    Slen,
)

# Two clients written by hand stay one surface: every public method of one is in the other, with the same signature.
TWINS: Final = (
    (Slen, AsyncSlen),
    (Operations, AsyncOperations),
    (Executions, AsyncExecutions),
    (Customers, AsyncCustomers),
)

# What the async twin says in place of the sync one.
SPELLED: Final = (
    ("collections.abc.Iterator", "collections.abc.AsyncIterator"),
    ("httpx.Client", "httpx.AsyncClient"),
    (
        "Callable[[slen._errors.SlenError, int], None]",
        "Callable[[slen._errors.SlenError, int], collections.abc.Awaitable[None] | None]",
    ),
    ("Operations", "AsyncOperations"),
    ("Executions", "AsyncExecutions"),
    ("Customers", "AsyncCustomers"),
    ("'Slen'", "'AsyncSlen'"),
)

# The methods of the async twin that are not coroutines: they build a client, or a loop that is iterated with async for.
NOT_AWAITED: Final = frozenset({"with_logger", "list_all", "entries_all", "__repr__", "__reduce__"})

# The dunders of a context manager, by the name each twin gives them.
CONTEXT: Final = {"__enter__": "__aenter__", "__exit__": "__aexit__"}


def public(kind: type) -> dict[str, Callable[..., Any]]:
    members = {name: member for name, member in vars(kind).items() if callable(member)}

    return {name: member for name, member in members.items() if not name.startswith("_") or name in CONTEXT}


def spelled(signature: inspect.Signature) -> str:
    text = str(signature)

    for sync, asynchronous in SPELLED:
        text = text.replace(asynchronous, "\0").replace(sync, asynchronous).replace("\0", asynchronous)

    return text


@pytest.mark.parametrize(("sync", "twin"), TWINS, ids=[sync.__name__ for sync, _ in TWINS])
def test_the_twins_have_the_same_public_methods(sync: type, twin: type) -> None:
    names = {CONTEXT.get(name, name) for name in public(sync)}

    assert names == {name for name in public(twin)} | ({"__aenter__", "__aexit__"} & set(vars(twin)))


@pytest.mark.parametrize(("sync", "twin"), TWINS, ids=[sync.__name__ for sync, _ in TWINS])
def test_each_method_of_the_twins_has_the_same_signature(sync: type, twin: type) -> None:
    for name, method in public(sync).items():
        other = getattr(twin, CONTEXT.get(name, name))

        assert spelled(inspect.signature(method)) == str(inspect.signature(other)), name


@pytest.mark.parametrize(("sync", "twin"), TWINS, ids=[sync.__name__ for sync, _ in TWINS])
def test_the_async_twin_awaits_every_call_that_goes_to_the_api(sync: type, twin: type) -> None:
    for name, method in public(twin).items():
        assert inspect.iscoroutinefunction(method) is (name not in NOT_AWAITED), name

    for name, method in public(sync).items():
        assert not inspect.iscoroutinefunction(method), name


def test_the_constructors_of_the_twins_take_the_same_options() -> None:
    assert spelled(inspect.signature(Slen.__init__)) == str(inspect.signature(AsyncSlen.__init__))


def test_the_modules_of_the_twins_are_twins_too() -> None:
    sync = {name: str(kind) for name, kind in Slen.__annotations__.items()}
    asynchronous = {name: str(kind) for name, kind in AsyncSlen.__annotations__.items()}

    assert sync.keys() == asynchronous.keys() == {"operations", "executions", "customers", "webhooks"}
    assert asynchronous["webhooks"] == sync["webhooks"]
