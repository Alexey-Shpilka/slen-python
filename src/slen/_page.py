from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True, kw_only=True)
class Page(Generic[T]):
    """One page of a list, newest first, and the cursor of the next one; None once the rows have run out."""

    data: tuple[T, ...]
    next_cursor: str | None
    request_id: str | None = field(default=None, compare=False)
