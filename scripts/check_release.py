"""check_release.py <tag>: the tag of a release is v + the version of pyproject.toml and of slen.__version__,
and CHANGELOG.md has the dated section of that version (`## [X.Y.Z] - YYYY-MM-DD`) and the link to it.

Read as the source is written — the package is not imported. Exit 0 — they agree; 1 — they do not, each named in a
line GitHub shows as an error; 2 — no tag given.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def versions(root: Path) -> tuple[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    module = ""

    for node in ast.parse((root / "src" / "slen" / "_version.py").read_text(encoding="utf-8")).body:
        if (
            isinstance(node, ast.AnnAssign | ast.Assign)
            and node.value is not None
            and "__version__" in ast.unparse(node)
        ):
            module = str(ast.literal_eval(node.value))

    return project, module


def changelog_problems(tag: str, root: Path) -> list[str]:
    version = re.escape(tag.removeprefix("v"))
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    dated = re.search(rf"^## \[{version}\] - [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$", text, re.MULTILINE)
    linked = re.search(rf"^\[{version}\]: https://\S+$", text, re.MULTILINE)
    found = [] if dated else [f"CHANGELOG.md has no section ## [{tag.removeprefix('v')}] - YYYY-MM-DD"]

    return found + ([] if linked else [f"CHANGELOG.md has no link [{tag.removeprefix('v')}]: at its bottom"])


def problems(tag: str, root: Path) -> list[str]:
    project, module = versions(root)
    found = [] if tag == f"v{project}" else [f"the tag {tag} is not v + the version {project} of pyproject.toml"]
    found += [] if tag == f"v{module}" else [f"the tag {tag} is not v + the version {module} of slen.__version__"]

    return found + changelog_problems(tag, root)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_release.py <tag>", file=sys.stderr)
        return 2

    found = problems(argv[0], ROOT)

    for line in found:
        print(f"::error::{line}")

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
