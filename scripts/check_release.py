"""check_release.py <tag>: the tag of a release is v + the version of pyproject.toml and of slen.__version__.

Read as the source is written — the package is not imported. Exit 0 — they agree; 1 — they do not, each named in a
line GitHub shows as an error; 2 — no tag given.
"""

import ast
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


def problems(tag: str, root: Path) -> list[str]:
    project, module = versions(root)
    found = [] if tag == f"v{project}" else [f"the tag {tag} is not v + the version {project} of pyproject.toml"]

    return found + (
        [] if tag == f"v{module}" else [f"the tag {tag} is not v + the version {module} of slen.__version__"]
    )


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
