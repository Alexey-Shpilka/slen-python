import importlib
import inspect
import json
import runpy
import tomllib
from pathlib import Path
from typing import Any, Final

import pytest

import slen
from slen import Slen
from support.paths import CONTRACT, ROOT, SCRIPTS

# The help slice: what the console's Help & Docs may say about this SDK without reading its source. The committed
# file is the slice of the source, and the slice says what the package does when it runs.

EXPORTER: Final = runpy.run_path(str(SCRIPTS / "export_help_slice.py"), run_name="exporter")
COMMITTED: Final[dict[str, Any]] = json.loads((ROOT / "help-slice.json").read_text(encoding="utf-8"))
LINES: Final[dict[str, Any]] = json.loads((CONTRACT / "calls.json").read_text(encoding="utf-8"))["calls"]


def test_the_committed_slice_is_the_slice_of_the_source() -> None:
    assert (ROOT / "help-slice.json").read_text(encoding="utf-8") == EXPORTER["text_of"](EXPORTER["build"]())


def test_check_names_a_slice_that_differs(tmp_path: Path) -> None:
    stale = tmp_path / "slice.json"
    stale.write_text("{}\n", encoding="utf-8")

    assert EXPORTER["main"](["--check", "--out", str(stale)]) == 1
    assert EXPORTER["main"](["--check"]) == 0
    assert EXPORTER["main"](["--write", "--out", str(stale)]) == 0
    assert EXPORTER["main"](["--check", "--out", str(stale)]) == 0
    assert EXPORTER["main"](["--sideways"]) == 2


def test_the_package_of_the_slice_is_the_one_of_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert COMMITTED["schema"] == 2
    assert COMMITTED["language"] == "python"
    assert COMMITTED["package"]["version"] == project["version"] == slen.__version__
    assert COMMITTED["package"]["runtime"] == {"name": "python", "constraint": ">=3.11"}
    assert [entry["name"] for entry in COMMITTED["package"]["dependencies"]] == ["httpx", "opentelemetry-api"]


def test_the_calls_are_the_lines_of_the_table_and_the_calls_that_send_nothing() -> None:
    lines = {name for name, line in LINES.items() if "python" in line["sdks"]}
    names = {call["name"] for call in COMMITTED["calls"]}

    assert names == lines | {"webhooks.verify", "webhooks.constructEvent", "close"}
    assert all(call["operation"] == LINES.get(call["name"], {}).get("operation") for call in COMMITTED["calls"])


@pytest.mark.parametrize("call", COMMITTED["calls"], ids=lambda call: call["name"])
def test_a_call_of_the_slice_is_a_method_a_client_reaches_by_its_python_name(call: dict[str, Any]) -> None:
    client = Slen(api_key="key-for-tests")
    owner, _, _ = call["name"].rpartition(".")
    reached: object = getattr(client, owner) if owner else client

    assert callable(getattr(reached, call["member"]))
    assert type(reached).__name__ == call["symbol"]
    assert (
        call["member"] == EXPORTER["python_name"](call["name"]).rpartition(".")[2]
        or call["name"] == "webhooks.constructEvent"
    )


def test_the_options_are_the_keywords_of_the_client() -> None:
    keywords = [
        name for name, given in inspect.signature(Slen.__init__).parameters.items() if given.kind is given.KEYWORD_ONLY
    ]

    assert [option["name"] for option in COMMITTED["options"]] == keywords
    assert next(option for option in COMMITTED["options"] if option["name"] == "api_key")["env"] == ["SLEN_API_KEY"]
    assert next(option for option in COMMITTED["options"] if option["name"] == "timeout")["default"]["value"] == 65.0


def test_the_symbols_are_the_exports_of_the_public_modules() -> None:
    exported = {
        (module, name)
        for module in ("slen", "slen.testing", "slen.otel")
        for name in importlib.import_module(module).__all__
    }

    assert {(symbol["module"], symbol["name"]) for symbol in COMMITTED["symbols"]} == exported


def test_a_member_of_a_symbol_is_there_at_run_time() -> None:
    missing = [
        f"{symbol['name']}.{member['name']}"
        for symbol in COMMITTED["symbols"]
        for member in symbol["members"]
        if not hasattr(getattr(importlib.import_module(symbol["module"]), symbol["name"]), member["name"])
        and member["kind"] != "field"
    ]

    assert missing == []


def test_a_signature_is_written_as_the_other_sdks_write_one() -> None:
    signatures = [call["signature"] for call in COMMITTED["calls"]]
    signatures += [member["signature"] for symbol in COMMITTED["symbols"] for member in symbol["members"]]
    adjust = next(call["signature"] for call in COMMITTED["calls"] if call["name"] == "customers.adjust")

    assert [text for text in signatures if text.startswith("def ") or "(self" in text or ": str=" in text] == []
    assert adjust.startswith("adjust(external_user_id: str, credits: str, *, credit_type: str = 'default', note: str")
    assert adjust.endswith(") -> CustomerAccount")
    assert next(call["signature"] for call in COMMITTED["calls"] if call["name"] == "close") == "close() -> None"


def test_a_constructor_over_the_internal_context_is_internal_and_one_a_caller_calls_is_not() -> None:
    constructors = {
        symbol["name"]: member
        for symbol in COMMITTED["symbols"]
        for member in symbol["members"]
        if member["kind"] == "constructor"
    }
    internal = {name for name, member in constructors.items() if member["internal"]}
    modules = {"Operations", "Executions", "Customers"}

    assert internal == modules | {f"Async{name}" for name in modules}
    assert all("Context" in constructors[name]["signature"] for name in internal)
    assert {"Slen", "AsyncSlen", "Webhooks", "FakeTransport", "MemorySpanRecorder", "LoggerSpanRecorder"} <= (
        set(constructors) - internal
    )
