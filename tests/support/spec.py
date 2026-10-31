import os
from functools import cache
from pathlib import Path
from typing import Any, Final, cast

import pytest
import yaml

VARIABLE: Final = "SLEN_OPENAPI_SPEC"
REFERENCE: Final = "#/components/schemas/"


@cache
def loaded() -> dict[str, Any] | None:
    named = os.environ.get(VARIABLE)

    if not named:
        return None

    path = Path(named)

    # A spec that is named and not there is a broken run, not a skipped one.
    if not path.is_file():
        raise FileNotFoundError(f"{VARIABLE} names {named}, which is not a file")

    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


def spec() -> dict[str, Any]:
    """The API's OpenAPI spec, or a skip when no spec is named."""
    found = loaded()

    if found is None:
        pytest.skip(f"{VARIABLE} names no spec")

    return found


def schema(name: str) -> dict[str, Any]:
    found: dict[str, Any] = spec()["components"]["schemas"][name]

    return found


def resolved(given: dict[str, Any]) -> dict[str, Any]:
    """A schema with its `$ref` followed and an `allOf` read as one object."""
    if "$ref" in given:
        return resolved(schema(str(given["$ref"]).removeprefix(REFERENCE)))

    if "allOf" not in given:
        return given

    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    for part in given["allOf"]:
        inner = resolved(part)
        merged["properties"].update(inner.get("properties", {}))
        merged["required"] += inner.get("required", [])

    return merged
