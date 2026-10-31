from typing import Any, Final, cast

from support.spec import REFERENCE, resolved, schema

KINDS: Final[dict[str, tuple[type, ...]]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def kinds_of(given: dict[str, Any]) -> list[str]:
    declared = given.get("type", [])

    return [declared] if isinstance(declared, str) else list(declared)


def fits(value: object, kind: str) -> bool:
    if kind == "null":
        return value is None

    if isinstance(value, bool) and kind != "boolean":
        return False

    return isinstance(value, KINDS.get(kind, (object,)))


def problems(value: object, given: dict[str, Any], where: str) -> list[str]:
    """What is wrong with a JSON value against a schema of the spec, in words: the shape, not the values."""
    if "$ref" in given:
        return problems(value, schema(str(given["$ref"]).removeprefix(REFERENCE)), where)

    if "allOf" in given:
        return problems(value, {**resolved(given), **{key: given[key] for key in given if key != "allOf"}}, where)

    for alternatives in ("oneOf", "anyOf"):
        if alternatives in given:
            found = [problems(value, option, where) for option in given[alternatives]]

            return [] if any(not one for one in found) else [f"{where} fits none of its {alternatives}"]

    if "const" in given and value != given["const"]:
        return [f"{where} is not {given['const']!r}"]

    kinds = kinds_of(given)

    if value is None:
        return [] if "null" in kinds or given.get("nullable") is True else [f"{where} is null"]

    if kinds and not any(fits(value, kind) for kind in kinds):
        return [f"{where} is not of type {'/'.join(kinds)}"]

    if "enum" in given and value not in given["enum"]:
        return [f"{where} is not one of its values"]

    if isinstance(value, dict):
        return object_problems(cast("dict[str, object]", value), given, where)

    if isinstance(value, list) and isinstance(given.get("items"), dict):
        items = cast("list[object]", value)

        return [
            found for index, item in enumerate(items) for found in problems(item, given["items"], f"{where}[{index}]")
        ]

    return []


def object_problems(value: dict[str, object], given: dict[str, Any], where: str) -> list[str]:
    properties: dict[str, Any] = given.get("properties", {})
    found = [f"{where}.{name} is missing" for name in given.get("required", []) if name not in value]
    open_object = given.get("additionalProperties") not in (None, False) or not properties

    found += [] if open_object else [f"{where}.{name} is not in the schema" for name in value if name not in properties]

    for name, inner in properties.items():
        if name in value:
            found += problems(value[name], inner, f"{where}.{name}")

    return found
