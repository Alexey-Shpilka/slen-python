from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Literal, TypeAlias, TypeVar, cast

E = TypeVar("E", bound=StrEnum)

# How a field is held: it must be there with a value; it must be there, perhaps null; it may be left out.
Presence: TypeAlias = Literal["required", "nullable", "optional"]

ABSENT: Final = object()


class WireError(Exception):
    pass


# One object of the wire, read field by field: a field the answer lacks or has of another type is a WireError,
# never a default — an answer of defaults would hide a call that went through. The message names the field only.
class Fields:
    __slots__ = ("_raw", "_where")

    def __init__(self, raw: object, where: str) -> None:
        if not isinstance(raw, dict):
            raise WireError(f"`{where}` is not an object")

        self._raw = cast("dict[str, object]", raw)
        self._where = where

    def raw(self) -> dict[str, object]:
        return dict(self._raw)

    def _get(self, name: str, presence: Presence) -> object:
        value = self._raw.get(name, ABSENT)

        if value is ABSENT and presence != "optional":
            raise WireError(f"`{self._where}.{name}` is missing")

        if value is None and presence == "required":
            raise WireError(f"`{self._where}.{name}` is null")

        return None if value is ABSENT else value

    def _typed(self, name: str, presence: Presence, kind: type[object]) -> object:
        value = self._get(name, presence)

        if value is not None and (not isinstance(value, kind) or isinstance(value, bool) is not (kind is bool)):
            raise WireError(f"`{self._where}.{name}` is not a {kind.__name__}")

        return value

    def text(self, name: str) -> str:
        return cast("str", self._typed(name, "required", str))

    def nullable_text(self, name: str) -> str | None:
        return cast("str | None", self._typed(name, "nullable", str))

    def optional_text(self, name: str) -> str | None:
        return cast("str | None", self._typed(name, "optional", str))

    def integer(self, name: str) -> int:
        return cast("int", self._typed(name, "required", int))

    def nullable_integer(self, name: str) -> int | None:
        return cast("int | None", self._typed(name, "nullable", int))

    def optional_integer(self, name: str) -> int | None:
        return cast("int | None", self._typed(name, "optional", int))

    def flag(self, name: str) -> bool:
        return cast("bool", self._typed(name, "required", bool))

    def moment(self, name: str) -> datetime:
        return cast("datetime", self._moment(name, "required"))

    def nullable_moment(self, name: str) -> datetime | None:
        return self._moment(name, "nullable")

    def optional_moment(self, name: str) -> datetime | None:
        return self._moment(name, "optional")

    def _moment(self, name: str, presence: Presence) -> datetime | None:
        text = cast("str | None", self._typed(name, presence, str))

        if text is None:
            return None

        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            raise WireError(f"`{self._where}.{name}` is not a time") from None

        if moment.tzinfo is None:
            raise WireError(f"`{self._where}.{name}` is a time without its offset")

        return moment

    def nullable_json(self, name: str) -> dict[str, Any] | None:
        return self._json(name, "nullable")

    def optional_json(self, name: str) -> dict[str, Any] | None:
        return self._json(name, "optional")

    # The backend encodes an empty object as `[]`: that is an empty object, a list with items is not.
    def _json(self, name: str, presence: Presence) -> dict[str, Any] | None:
        value = self._get(name, presence)

        if value == []:
            return {}

        if value is not None and not isinstance(value, dict):
            raise WireError(f"`{self._where}.{name}` is not an object")

        return cast("dict[str, Any] | None", value)

    def nested(self, name: str) -> "Fields":
        return Fields(self._get(name, "required"), f"{self._where}.{name}")

    def nullable_nested(self, name: str) -> "Fields | None":
        value = self._get(name, "nullable")

        return None if value is None else Fields(value, f"{self._where}.{name}")

    def rows(self, name: str) -> list["Fields"]:
        value = self._typed(name, "required", list)

        return [Fields(row, f"{self._where}.{name}[]") for row in cast("list[object]", value)]

    def choice(self, name: str, kind: type[E]) -> E:
        text = self.text(name)

        try:
            return kind(text)
        except ValueError:
            raise WireError(f"`{self._where}.{name}` is not one of the values this SDK knows") from None
