import ast
import io
import re
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import pytest

from support.paths import EXAMPLES, PUBLIC_MODULES, ROOT, SRC

# The house rules of the package, held on its source with the AST. The reasons are in AGENTS.md.

MAX_POSITIONAL: Final = 3
MAX_INTERNAL_PARAMETERS: Final = 3
MAX_COMMENT_LINES: Final = 6
MAX_COMMENT_SHARE: Final = 0.10

# What a public repository must not carry: the patterns of the guard a public tree is made behind.
# Each is spelt so that it does not find itself.
INTERNAL: Final = (
    (re.compile(r"/h[o]me/", re.IGNORECASE), "a path of a machine"),
    (re.compile(r"d[o]cs/v\d", re.IGNORECASE), "a link to the plans"),
    (re.compile(r"slen\.(?:backend|frontend|infra|docs|sdk)", re.IGNORECASE), "a private repository"),
    (re.compile(r"backend/[o]penapi", re.IGNORECASE), "the tree of the backend"),
    (re.compile(r"DEPLOY_[K]EY", re.IGNORECASE), "a deploy key"),
    (re.compile(r"localhost:3808[0]", re.IGNORECASE), "the local stack"),
    (re.compile(r"sn[o]vio|sp[e]ndguard|l[i]mly", re.IGNORECASE), "an earlier name"),
    (re.compile(r"(?<!\w)[НРПЗВФХ](?:-\d|\d+\.\d)", re.IGNORECASE), "a number of a finding, a decision or a task"),
    (re.compile(r"sl_live_[A-Za-z0-9]{20,}"), "a key that looks real"),
    (re.compile(r"(?<![^\W_]|[./])v\d{2,}/", re.IGNORECASE), "a branch of the plans"),
    (re.compile(r"_v\d+_", re.IGNORECASE), "the number of a plan in a name"),
    (re.compile(r"\b(?:since|until) v\d{2,}(?![.\d])", re.IGNORECASE), "the number of a plan"),
    (
        re.compile(r"\b(?:backend|frontend|infra|sdk|master|main)[ @:#][0-9a-f]{7,40}\b", re.IGNORECASE),
        "a branch pinned to a commit",
    ),
)

# Words that tell the history of the code instead of what it does.
HISTORY: Final = (
    (re.compile(r"\bused to\b", re.IGNORECASE), '"used to"'),
    (re.compile(r"\buntil v\d+", re.IGNORECASE), '"until vNN"'),
    (re.compile(r"\bsince v\d+", re.IGNORECASE), '"since vNN"'),
)

# What the tools leave in a working tree and a public tree never gets.
LEFT_BEHIND: Final = (
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "node_modules",
)

# Calls whose value a module may keep: each answers something that cannot change.
# A sentinel `object()` and the frozen dataclasses `Clock` and `Sending` are among them.
IMMUTABLE_CALLS: Final = frozenset(
    {
        "frozenset",
        "MappingProxyType",
        "re.compile",
        "TypeVar",
        "field",
        "NewType",
        "tuple",
        "object",
        "Clock",
        "Sending",
    }
)

# The one thing a module of the package may do when imported: give the library's logger a handler that drops records.
IMPORT_EFFECTS: Final = frozenset({"logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())"})

Callable = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class Function:
    node: Callable | ast.Lambda
    public: bool
    method: bool


def parse(text: str) -> ast.Module:
    return ast.parse(text, type_comments=False)


def sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def exported_names() -> frozenset[str]:
    names: set[str] = set()

    for module in PUBLIC_MODULES:
        if not module.exists():
            continue

        for node in parse(module.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign):
                continue

            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                value: tuple[str, ...] = ast.literal_eval(ast.unparse(node.value))
                names.update(value)

    return frozenset(names)


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def functions_of(tree: ast.Module, exported: frozenset[str]) -> Iterator[Function]:
    for node in top_level(tree.body):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield Function(node, public=node.name in exported, method=False)
            yield from nested_functions(node)

        if isinstance(node, ast.ClassDef):
            yield from class_functions(node, public=node.name in exported)

    for inner in ast.walk(tree):
        if isinstance(inner, ast.Lambda):
            yield Function(inner, public=False, method=False)


def top_level(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    for node in body:
        yield node

        if isinstance(node, ast.If | ast.Try):
            yield from top_level(node.body)
            yield from top_level(node.orelse)


def class_functions(node: ast.ClassDef, *, public: bool) -> Iterator[Function]:
    for member in node.body:
        if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
            own = public and (not member.name.startswith("_") or member.name == "__init__")
            yield Function(member, public=own, method=True)
            yield from nested_functions(member)

        if isinstance(member, ast.ClassDef):
            yield from class_functions(member, public=False)


def nested_functions(node: Callable) -> Iterator[Function]:
    for inner in ast.walk(node):
        if inner is not node and isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef):
            yield Function(inner, public=False, method=False)


def classes_of(tree: ast.Module, exported: frozenset[str]) -> Iterator[tuple[ast.ClassDef, bool]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield node, node.name in exported and node in tree.body


# ---------------------------------------------------------------------------
# The rules, each a function of a source, so that the self-check below can plant a breach of each.


def else_problems(tree: ast.Module) -> list[str]:
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.orelse:
            found.append(f"{node.lineno}: an else or an elif")

        if isinstance(node, ast.For | ast.AsyncFor | ast.While) and node.orelse:
            found.append(f"{node.lineno}: a loop with an else")

        if isinstance(node, ast.Try | ast.TryStar) and node.orelse:
            found.append(f"{node.lineno}: a try with an else")

    return found


def parameters_of(function: Function) -> tuple[int, int]:
    arguments = function.node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    own = positional[1:] if function.method and positional and positional[0].arg in ("self", "cls") else positional
    total = len(own) + len(arguments.kwonlyargs) + (arguments.vararg is not None) + (arguments.kwarg is not None)

    return len(own), total


def parameter_problems(tree: ast.Module, exported: frozenset[str]) -> list[str]:
    found: list[str] = []

    for function in functions_of(tree, exported):
        positional, total = parameters_of(function)
        name = getattr(function.node, "name", "lambda")

        if positional > MAX_POSITIONAL:
            found.append(f"{function.node.lineno}: {name} takes {positional} positional parameters")

        if not function.public and total > MAX_INTERNAL_PARAMETERS:
            found.append(f"{function.node.lineno}: {name}, not public, takes {total} parameters")

    return found


def docstring_lines(node: ast.AST) -> tuple[int, str] | None:
    body: object = getattr(node, "body", None)

    if not isinstance(body, list) or not body:
        return None

    first = cast("list[object]", body)[0]

    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
        and first.end_lineno is not None
    ):
        return first.end_lineno - first.lineno + 1, first.value.value

    return None


def docstring_problems(tree: ast.Module, *, public_module: bool, exported: frozenset[str]) -> list[str]:
    found: list[str] = []
    module = docstring_lines(tree)

    if public_module and module is not None and module[0] != 1:
        found.append("1: a public module has a docstring of one line, or none")

    if not public_module and module is not None:
        found.append("1: an internal module has no docstring")

    named: list[tuple[ast.AST, str, bool]] = [(node, node.name, public) for node, public in classes_of(tree, exported)]
    named += [
        (function.node, function.node.name, function.public and not is_dunder(function.node.name))
        for function in functions_of(tree, exported)
        if not isinstance(function.node, ast.Lambda)
    ]

    for node, name, public in named:
        doc = docstring_lines(node)
        line = getattr(node, "lineno", 0)

        if public and (doc is None or doc[0] != 1 or "\n" in doc[1]):
            found.append(f"{line}: {name} is public and has a docstring of one line")

        if not public and doc is not None:
            found.append(f"{line}: {name} is not public and has no docstring")

    return found


def comment_line_numbers(text: str) -> list[int]:
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)

    return sorted({token.start[0] for token in tokens if token.type == tokenize.COMMENT})


def comment_runs(text: str) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []

    for line in comment_line_numbers(text):
        if runs and runs[-1][0] + runs[-1][1] == line:
            start, length = runs[-1]
            runs[-1] = (start, length + 1)
            continue

        runs.append((line, 1))

    return runs


def comment_problems(text: str) -> list[str]:
    runs = comment_runs(text)
    found = [f"{start}: {length} lines of comment" for start, length in runs if length > MAX_COMMENT_LINES]
    lines = text.splitlines()

    for number in comment_line_numbers(text):
        found += [f"{number}: {what}" for pattern, what in HISTORY if pattern.search(lines[number - 1])]

    return found


def explanation_lines(text: str) -> int:
    tree = parse(text)
    docs = [docstring_lines(node) for node in ast.walk(tree)]

    return len(comment_line_numbers(text)) + sum(doc[0] for doc in docs if doc is not None)


def dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"

    return ""


def immutable(value: ast.expr) -> bool:
    if isinstance(value, ast.Constant | ast.JoinedStr | ast.Name | ast.Attribute | ast.Subscript | ast.Lambda):
        return True

    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
        return True

    if isinstance(value, ast.Tuple):
        return all(immutable(item) for item in value.elts)

    if isinstance(value, ast.Call):
        return dotted(value.func) in IMMUTABLE_CALLS

    return False


def state_problems(tree: ast.Module) -> list[str]:
    found: list[str] = []
    bodies: list[list[ast.stmt]] = [list(top_level(tree.body))]
    bodies += [node.body for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

    for body in bodies:
        for node in body:
            value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None

            if value is not None and not immutable(value):
                found.append(f"{node.lineno}: {ast.unparse(value)[:40]} is state that can change")

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            effect = ast.unparse(node.value)
            found += [] if effect in IMPORT_EFFECTS else [f"{node.lineno}: {effect[:40]} runs on import"]

    return found


def staticmethod_problems(tree: ast.Module) -> list[str]:
    return [
        f"{node.lineno}: @staticmethod"
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(dotted(decorator) == "staticmethod" for decorator in node.decorator_list)
    ]


def internal_problems(text: str) -> list[str]:
    return [
        f"{number}: {what}"
        for number, line in enumerate(text.splitlines(), start=1)
        for pattern, what in INTERNAL
        if pattern.search(line)
    ]


def package_files() -> list[Path]:
    found: list[Path] = []

    for path in sorted(ROOT.rglob("*")):
        parts = path.relative_to(ROOT).parts

        if any(part in LEFT_BEHIND or part.endswith(".egg-info") for part in parts) or not path.is_file():
            continue

        found.append(path)

    return found


def problems_of_source(path: Path, exported: frozenset[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = parse(text)

    return [
        *else_problems(tree),
        *parameter_problems(tree, exported),
        *docstring_problems(tree, public_module=path in PUBLIC_MODULES, exported=exported),
        *comment_problems(text),
        *state_problems(tree),
        *staticmethod_problems(tree),
    ]


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", sources(), ids=lambda path: str(path.relative_to(SRC)))
def test_a_source_keeps_the_house_rules(path: Path) -> None:
    assert problems_of_source(path, exported_names()) == []


def test_comments_and_docstrings_are_at_most_a_tenth_of_the_source() -> None:
    texts = [path.read_text(encoding="utf-8") for path in sources()]
    explained = sum(explanation_lines(text) for text in texts)
    total = sum(len(text.splitlines()) for text in texts)

    assert explained <= total * MAX_COMMENT_SHARE, f"{explained} of {total} lines explain"


def test_no_file_of_the_package_carries_anything_internal() -> None:
    found = {
        str(path.relative_to(ROOT)): problems
        for path in package_files()
        if (problems := internal_problems(path.read_text(encoding="utf-8")))
    }

    assert found == {}


def example_else_problems(tree: ast.Module) -> list[str]:
    conditional = [f"{node.lineno}: a conditional expression" for node in ast.walk(tree) if isinstance(node, ast.IfExp)]

    return else_problems(tree) + conditional


def test_an_example_branches_without_else() -> None:
    found = {
        str(path.relative_to(EXAMPLES)): problems
        for path in sorted(EXAMPLES.glob("*/python.py"))
        if (problems := example_else_problems(parse(path.read_text(encoding="utf-8"))))
    }

    assert found == {}


def test_every_exported_name_is_defined_once() -> None:
    defined: dict[str, int] = {}

    for path in sources():
        for node in parse(path.read_text(encoding="utf-8")).body:
            name = getattr(node, "name", None)

            if isinstance(name, str) and name in exported_names():
                defined[name] = defined.get(name, 0) + 1

    assert {name: count for name, count in defined.items() if count != 1} == {}


# ---------------------------------------------------------------------------
# The check itself: a breach of each rule, planted, is found.

PLANTED: Final = {
    "an else": "def f(a):\n    if a:\n        return 1\n    else:\n        return 2\n",
    "an elif": "def f(a):\n    if a:\n        return 1\n    elif a > 1:\n        return 2\n    return 3\n",
    "a for with an else": "def f(a):\n    for x in a:\n        pass\n    else:\n        return 1\n",
    "a while with an else": "def f(a):\n    while a:\n        pass\n    else:\n        return 1\n",
    "a try with an else": "def f(a):\n    try:\n        a()\n    except E:\n        pass\n    else:\n        return 1",
    "four positional parameters": "def _f(a, b, c, d):\n    return a\n",
    "four parameters of an internal function": "def _f(a, *, b, c, d):\n    return a\n",
    "four parameters of a lambda": "_F = lambda a, b, c, d: a\n",
    "an internal docstring": 'def _f():\n    """Says something."""\n',
    "a docstring of an internal module": '"""A module."""\n',
    "seven lines of comment": "".join(f"# {n}\n" for n in range(7)),
    "history in a comment": "# This used to be another way.\nX = 1\n",
    "a list at module level": "X = [1, 2]\n",
    "a dict at class level": "class _C:\n    x = {}\n",
    "a call on import": "print('hello')\n",
    "a static method": "class _C:\n    @staticmethod\n    def f():\n        return 1\n",
}


@pytest.mark.parametrize("source", PLANTED.values(), ids=list(PLANTED))
def test_the_hygiene_check_finds_a_planted_breach(source: str, tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(source, encoding="utf-8")

    assert problems_of_source(planted, frozenset()) != []


def test_the_hygiene_check_wants_a_one_line_docstring_on_the_public_surface() -> None:
    tree = parse('class Public:\n    def call(self):\n        """Two\n        lines."""\n')

    assert docstring_problems(tree, public_module=False, exported=frozenset({"Public"})) != []
    assert docstring_problems(parse("def shown(): ...\n"), public_module=False, exported=frozenset({"shown"})) != []


def test_the_hygiene_check_finds_a_conditional_expression_in_an_example() -> None:
    assert example_else_problems(parse("x = 1 if y else 2\n")) != []
    assert else_problems(parse("x = 1 if y else 2\n")) == []


# Made up, and spelt in pieces so that this file carries none of them.
PLANTED_INTERNAL: Final = (
    ("/h" + "ome/someone/x", "a path of a machine"),
    ("d" + "ocs/v99/README.md", "a link to the plans"),
    ("slen" + ".backend", "a private repository"),
    ("sl_live_" + "A" * 24, "a key that looks real"),
    ("branch v" + "99/sdk", "a branch of the plans"),
    ("\u0417" + "-99", "a number of a finding, a decision or a task"),
    ("master " + "1a2b3c4", "a branch pinned to a commit"),
)


@pytest.mark.parametrize(("text", "rule"), PLANTED_INTERNAL, ids=[rule for _, rule in PLANTED_INTERNAL])
def test_the_hygiene_check_finds_what_is_internal(text: str, rule: str) -> None:
    assert rule in " ".join(internal_problems(text))


def test_the_hygiene_check_lets_what_is_public_through() -> None:
    assert internal_problems("GET /api/v1/customers and sl_live_help_example") == []


def test_the_hygiene_check_lets_public_keyword_options_through() -> None:
    tree = parse("class Shown:\n    def call(self, a, b, *, c=None, d=None, e=None):\n        return a\n")

    assert parameter_problems(tree, frozenset({"Shown"})) == []
    assert parameter_problems(tree, frozenset()) != []
