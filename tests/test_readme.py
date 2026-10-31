import ast
import inspect
import re
from typing import Final

import pytest

import slen
import slen.testing
from slen import AsyncSlen, ExecutionStatus, Slen
from support.paths import ROOT

# The README is held to the code: every call it shows is one of the client, every name it imports is exported,
# and nothing the SDK does not have, or keeps for tests, is shown.

README: Final = (ROOT / "README.md").read_text(encoding="utf-8")
BLOCKS: Final = re.findall(r"```python\n(.*?)```", README, re.DOTALL)
NAMED_NOWHERE: Final = (re.compile(r"base[_ ]?url|SLEN_BASE_URL", re.IGNORECASE), re.compile(r"\bsg_(?:live|test)_"))
RETIRED: Final = re.compile(
    r"cost_estimates|wait_until_finished|is_allowed|\bauthorizations\b|default_operation|dry_run"
)


def test_the_readme_has_its_blocks() -> None:
    assert len(BLOCKS) >= 10


@pytest.mark.parametrize("block", BLOCKS)
def test_a_block_of_the_readme_is_python_and_branches_without_else(block: str) -> None:
    tree = ast.parse(block)
    branches = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.If | ast.For | ast.While | ast.Try) and node.orelse) or isinstance(node, ast.IfExp)
    ]

    assert branches == []


def test_every_call_the_readme_shows_is_a_call_of_both_clients() -> None:
    calls = set(re.findall(r"\bslen\.((?:[a-z_]+\.)?[a-z_]+)\(", README))
    missing = [call for call in sorted(calls) for client in (Slen, AsyncSlen) if not reaches(client, call)]

    assert calls >= {"operations.execute", "executions.wait", "customers.entries_all", "with_logger"}
    assert missing == []


def reaches(client: type, call: str) -> bool:
    built = client(api_key="key-for-tests")
    found: object = built

    for part in call.split("."):
        found = getattr(found, part, None)

    return callable(found)


def test_every_name_the_readme_imports_is_exported() -> None:
    imported = {
        (node.module, alias.name)
        for block in BLOCKS
        for node in ast.walk(ast.parse(block))
        if isinstance(node, ast.ImportFrom) and node.module in ("slen", "slen.testing", "slen.otel")
        for alias in node.names
    }
    modules = {"slen": slen.__all__, "slen.testing": slen.testing.__all__, "slen.otel": ("OtelSpanRecorder",)}

    assert [(module, name) for module, name in imported if name not in modules[str(module)]] == []


def test_the_readme_names_no_address_old_key_or_retired_call() -> None:
    assert [pattern.pattern for pattern in NAMED_NOWHERE if pattern.search(README)] == []
    assert RETIRED.findall(README) == []


def test_the_status_line_lists_every_status() -> None:
    line = next(line for line in README.splitlines() if "print(run.status)  #" in line)

    assert line.split("#", 1)[1].strip() == " | ".join(str(status) for status in ExecutionStatus)


def test_a_run_of_the_readme_carries_messages() -> None:
    runs = re.findall(r"operations\.execute(?:_async)?\(\s*\"[^\"]+\",\s*(\{[^\n]*)", README)

    assert runs != []
    assert all('"messages"' in run for run in runs)


def test_the_table_of_options_is_the_constructor_but_the_address() -> None:
    table = README.split("| Option | Default | |", 1)[1].split("\n\n", 1)[0]
    named = set(re.findall(r"^\| `([a-z_]+)`(?:, `([a-z_]+)`)?", table, re.MULTILINE))
    options = {name for pair in named for name in pair if name}
    keywords = set(inspect.signature(Slen.__init__).parameters) - {"self"}

    assert options | {"base_url"} == keywords
