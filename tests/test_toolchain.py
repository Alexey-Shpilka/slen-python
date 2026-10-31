import ast
import tomllib
from pathlib import Path
from typing import Any, Final

import slen
from support.paths import ROOT, SRC

PYPROJECT: Final[dict[str, Any]] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT: Final[dict[str, Any]] = PYPROJECT["project"]
TOOLS: Final[dict[str, Any]] = PYPROJECT["tool"]

# The floor of the package: every tool reads the same one.
FLOOR: Final = "3.11"

# What the tools leave in a working tree: git must never take it.
LEFT_BEHIND: Final = (
    "__pycache__/",
    ".venv/",
    "*.egg-info/",
    "build/",
    "dist/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
)


def test_the_version_of_the_package_is_the_version_of_the_module() -> None:
    assert PROJECT["version"] == slen.__version__


def test_every_tool_reads_the_floor_of_the_package() -> None:
    assert PROJECT["requires-python"] == f">={FLOOR}"
    assert TOOLS["ruff"]["target-version"] == "py" + FLOOR.replace(".", "")
    assert TOOLS["mypy"]["python_version"] == FLOOR
    assert TOOLS["pyright"]["pythonVersion"] == FLOOR


def test_the_package_depends_on_httpx_alone() -> None:
    assert PROJECT["dependencies"] == ["httpx>=0.27,<1"]
    assert PROJECT["optional-dependencies"] == {"otel": ["opentelemetry-api>=1.27"]}


def test_the_tools_are_pinned() -> None:
    loose = [entry for entry in PYPROJECT["dependency-groups"]["dev"] if "==" not in entry]

    # Django 6 needs Python 3.12; the floor gets 5.2, the rest 6.
    assert loose == ["django>=5.2,<7"]


def test_the_type_checkers_are_strict() -> None:
    assert TOOLS["mypy"]["strict"] is True
    assert TOOLS["pyright"]["typeCheckingMode"] == "strict"


def test_the_wheel_carries_the_package_and_the_sdist_its_sources() -> None:
    build = TOOLS["hatch"]["build"]["targets"]

    assert build["wheel"]["packages"] == ["src/slen"]
    assert build["sdist"]["only-include"] == ["src", "pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md"]
    assert (SRC / "py.typed").is_file()


def test_git_takes_nothing_the_tools_leave() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert [entry for entry in LEFT_BEHIND if entry not in ignored] == []


def test_the_source_parses_on_the_floor() -> None:
    for path in sorted(SRC.rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))


def test_the_agents_file_stays_short() -> None:
    for path in (ROOT / "AGENTS.md", ROOT / ".github" / "AGENTS.md"):
        assert len(Path(path).read_text(encoding="utf-8").splitlines()) <= 150, path
