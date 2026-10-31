"""export_help_slice.py [--write | --check] [--out FILE]: the help slice of this SDK, read off its source.

What the console's Help & Docs may say about the Python SDK without reading its source: the package, the options of
the client, every call it reaches and every public symbol. The standard library only (ast, tomllib, json), and the
package is never imported: the slice is read as the source is written. Exit 0 — written, or the same; 1 — --check
found a difference, named; 2 — a command line it does not know, a source it could not read, a file it could not write.
"""

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "slen"
SLICE = ROOT / "help-slice.json"
PUBLIC = {"slen": SRC / "__init__.py", "slen.testing": SRC / "testing.py", "slen.otel": SRC / "otel.py"}
CLIENT = "Slen"
MODULES = {"operations": "Operations", "executions": "Executions", "customers": "Customers", "webhooks": "Webhooks"}
# The public calls that make no request of the API, by the name the reference gives them.
NOT_CALLS = {"webhooks.verify": "verify", "webhooks.constructEvent": "construct_event", "close": "close"}
NOT_A_CALL = {"with_logger"}
ENV = {"api_key": ["SLEN_API_KEY"]}


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def exported(module: Path) -> list[str]:
    for node in parse(module).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            return list(ast.literal_eval(node.value))

    return []


def definitions() -> dict[str, tuple[ast.stmt, Path]]:
    """Every top-level definition of the package, by name: classes, functions, assignments."""
    found: dict[str, tuple[ast.stmt, Path]] = {}

    for path in sorted(SRC.rglob("*.py")):
        for node in parse(path).body:
            for name in names_of(node):
                found.setdefault(name, (node, path))

    return found


def names_of(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        return [node.name]

    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]

    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]

    return []


# As the other SDKs write a signature, `name(parameters) -> Return`: no `def`, no `self`, PEP 8's spaces around
# the `=` of an annotated default; a coroutine says `async` before its name.
def signature_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""

    return f"{prefix}{node.name}({parameters_of(node.args)}){returns}"


def parameter(argument: ast.arg, default: ast.expr | None) -> str:
    annotation = f": {ast.unparse(argument.annotation)}" if argument.annotation is not None else ""
    equals = " = " if annotation else "="

    return f"{argument.arg}{annotation}" + ("" if default is None else f"{equals}{ast.unparse(default)}")


def parameters_of(arguments: ast.arguments) -> str:
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    defaults += list(arguments.defaults)
    parts: list[str] = []

    for index, (argument, default) in enumerate(zip(positional, defaults, strict=True)):
        if index > 0 or argument.arg not in ("self", "cls"):
            parts.append(parameter(argument, default))

        if arguments.posonlyargs and index == len(arguments.posonlyargs) - 1:
            parts.append("/")

    if arguments.vararg is not None:
        parts.append(f"*{parameter(arguments.vararg, None)}")

    if arguments.vararg is None and arguments.kwonlyargs:
        parts.append("*")

    parts += [
        parameter(argument, default)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    ]

    if arguments.kwarg is not None:
        parts.append(f"**{parameter(arguments.kwarg, None)}")

    return ", ".join(parts)


def is_dataclass(node: ast.ClassDef) -> bool:
    return any("dataclass" in ast.unparse(decorator) for decorator in node.decorator_list)


def kind_and_modifiers(node: ast.ClassDef) -> tuple[str, list[str]]:
    bases = [ast.unparse(base) for base in node.bases]

    if "StrEnum" in bases:
        return "enum", []

    if any(base.startswith("Protocol") for base in bases):
        return "protocol", []

    if is_dataclass(node):
        return "class", ["dataclass", "frozen"]

    return "class", []


def member(name: str, kind: str, signature: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "static": False,
        "optional": False,
        "deprecated": False,
        "internal": False,
        "signature": signature,
    }


# A constructor that takes a type of the package that is not exported is the client's to call, never the caller's:
# the modules are built by `Slen` and `AsyncSlen` over their internal context.
def takes_the_internal(item: ast.FunctionDef | ast.AsyncFunctionDef, hidden: frozenset[str]) -> bool:
    arguments = item.args
    annotations = [argument.annotation for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]]
    named = {
        node.id
        for annotation in annotations
        if annotation is not None
        for node in ast.walk(annotation)
        if isinstance(node, ast.Name)
    }

    return bool(named & hidden)


def members_of(node: ast.ClassDef, hidden: frozenset[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    enum = kind_and_modifiers(node)[0] == "enum"

    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
            default = "" if item.value is None else f" = {default_of(item.value)}"
            found.append(member(item.target.id, "field", f"{item.target.id}: {ast.unparse(item.annotation)}{default}"))

        if enum and isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name):
            found.append(member(item.targets[0].id, "member", ast.unparse(item)))

        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and (
            not item.name.startswith("_") or item.name == "__init__"
        ):
            decorators = {ast.unparse(decorator) for decorator in item.decorator_list}
            kind = "constructor" if item.name == "__init__" else "property" if "property" in decorators else "method"
            entry = member(item.name, kind, signature_of(item))
            entry["internal"] = kind == "constructor" and takes_the_internal(item, hidden)
            found.append(entry)

    return found


def default_of(value: ast.expr) -> str:
    text = ast.unparse(value)
    match = re.fullmatch(r"field\((.*)\)", text)

    return re.sub(r".*default=([^,]+).*", r"\1", match.group(1)) if match and "default=" in text else text


def symbol(name: str, module: str, found: tuple[ast.stmt, Path], hidden: frozenset[str]) -> dict[str, Any]:
    node, path = found
    entry: dict[str, Any] = {
        "name": name,
        "module": module,
        "kind": "constant",
        "source": relative(path),
        "deprecated": False,
        "internal": False,
        "alias_of": None,
        "modifiers": [],
        "type_parameters": [],
        "extends": [],
        "implements": [],
        "signature": None,
        "members": [],
    }

    if isinstance(node, ast.ClassDef):
        kind, modifiers = kind_and_modifiers(node)
        bases = [ast.unparse(base) for base in node.bases]
        generic = [re.sub(r"Generic\[(.*)\]", r"\1", base) for base in bases if base.startswith("Generic[")]
        extends = [base for base in bases if not base.startswith("Generic[")]
        entry.update(
            kind=kind, modifiers=modifiers, extends=extends, type_parameters=generic, members=members_of(node, hidden)
        )

    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        entry.update(kind="function", signature=signature_of(node))

    if isinstance(node, ast.AnnAssign) and "TypeAlias" in ast.unparse(node.annotation) and node.value is not None:
        entry.update(kind="type", signature=f"{name}: TypeAlias = {ast.unparse(node.value)}")

    if isinstance(node, ast.AnnAssign | ast.Assign) and entry["kind"] == "constant" and node.value is not None:
        entry.update(signature=f"{name} = {ast.unparse(node.value)}")

    return entry


def symbols(defined: dict[str, tuple[ast.stmt, Path]]) -> list[dict[str, Any]]:
    public = {name for path in PUBLIC.values() for name in exported(path)}
    hidden = frozenset(name for name in defined if name not in public and name[:1].isupper())
    found = [symbol(name, module, defined[name], hidden) for module, path in PUBLIC.items() for name in exported(path)]

    return sorted(found, key=lambda entry: (entry["module"], entry["name"]))


def python_name(key: str) -> str:
    return ".".join(re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", segment).lower() for segment in key.split("."))


def methods(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {item.name: item for item in node.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)}


def calls(defined: dict[str, tuple[ast.stmt, Path]]) -> list[dict[str, Any]]:
    table = json.loads((ROOT / "contract" / "calls.json").read_text(encoding="utf-8"))["calls"]
    lines = {name: line["operation"] for name, line in table.items() if "python" in line["sdks"]}
    found: list[dict[str, Any]] = []

    for name in sorted([*lines, *NOT_CALLS]):
        owner, _, member_name = python_name(name).rpartition(".")
        member_name = NOT_CALLS.get(name, member_name)
        symbol_name = MODULES.get(owner, CLIENT)
        node = defined[symbol_name][0]

        if not isinstance(node, ast.ClassDef) or member_name not in methods(node):
            raise LookupError(f"{name}: {symbol_name} has no {member_name}")

        found.append(
            {
                "name": name,
                "symbol": symbol_name,
                "member": member_name,
                "deprecated": False,
                "internal": False,
                "signature": signature_of(methods(node)[member_name]),
                "operation": lines.get(name),
            }
        )

    return found


def options(defined: dict[str, tuple[ast.stmt, Path]]) -> list[dict[str, Any]]:
    node = defined[CLIENT][0]

    if not isinstance(node, ast.ClassDef):
        raise LookupError(CLIENT)

    arguments = methods(node)["__init__"].args
    constants = constants_of(SRC / "_config.py")
    found: list[dict[str, Any]] = []

    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        code = ast.unparse(default) if default is not None else None
        value = constants.get(code, None) if code in constants else literal(default)
        found.append(
            {
                "name": argument.arg,
                "type": ast.unparse(argument.annotation) if argument.annotation is not None else None,
                "required": default is None,
                "default": None if code is None or code == "None" else {"code": code, "value": value},
                "default_known": True,
                "env": ENV.get(argument.arg, []),
                "description": None,
            }
        )

    return found


def literal(node: ast.expr | None) -> object:
    try:
        return ast.literal_eval(node) if node is not None else None
    except ValueError:
        return None


def constants_of(path: Path) -> dict[str, Any]:
    found: dict[str, Any] = {}

    for node in parse(path).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            found[node.target.id] = literal(node.value)

    return found


def package() -> dict[str, Any]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = [requirement(line, optional=False, extra=None) for line in project["dependencies"]]

    for extra, lines in sorted(project.get("optional-dependencies", {}).items()):
        dependencies += [requirement(line, optional=True, extra=extra) for line in lines]

    return {
        "name": project["name"],
        "version": project["version"],
        "manifest": "pyproject.toml",
        "runtime": {"name": "python", "constraint": project["requires-python"]},
        "dependencies": sorted(dependencies, key=lambda entry: entry["name"]),
    }


def requirement(line: str, *, optional: bool, extra: str | None) -> dict[str, Any]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", line.strip())

    if match is None:
        raise LookupError(f"a requirement of pyproject.toml it cannot read: {line}")

    name, constraint = match.groups()

    return {"name": name, "constraint": constraint.strip(), "optional": optional, "extra": extra}


def build() -> dict[str, Any]:
    defined = definitions()

    return {
        "schema": 2,
        "language": "python",
        "package": package(),
        "client": {"class": CLIENT, "options": CLIENT},
        "options": options(defined),
        "config_file": None,
        "calls": calls(defined),
        "symbols": symbols(defined),
    }


def text_of(sliced: dict[str, Any]) -> str:
    return json.dumps(sliced, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="export_help_slice.py", exit_on_error=False)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=SLICE)

    try:
        given = parser.parse_args(argv)
        fresh = text_of(build())
    except SystemExit:
        return 2
    except (argparse.ArgumentError, OSError, LookupError, SyntaxError) as error:
        print(f"export_help_slice: {error}", file=sys.stderr)
        return 2

    if given.write:
        given.out.write_text(fresh, encoding="utf-8")
        return 0

    if not given.check:
        sys.stdout.write(fresh)
        return 0

    committed = given.out.read_text(encoding="utf-8") if given.out.is_file() else ""

    if committed == fresh:
        return 0

    print(f"export_help_slice: {given.out.name} is not the slice of the source; run with --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
