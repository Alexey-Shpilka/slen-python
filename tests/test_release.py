import runpy
from pathlib import Path
from typing import Final

import pytest

import slen
from support.paths import ROOT, SCRIPTS

# The guards of a release, on vectors: a tag that is not the version is refused before anything is built.

GUARD: Final = runpy.run_path(str(SCRIPTS / "check_release.py"), run_name="guard")
WORKFLOW: Final = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def tree(tmp_path: Path, project: str, module: str) -> Path:
    (tmp_path / "src" / "slen").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "slen"\nversion = "{project}"\n', encoding="utf-8")
    (tmp_path / "src" / "slen" / "_version.py").write_text(
        f'from typing import Final\n\n__version__: Final = "{module}"\n', encoding="utf-8"
    )

    return tmp_path


def test_the_tag_of_this_tree_is_its_version() -> None:
    assert GUARD["problems"](f"v{slen.__version__}", ROOT) == []
    assert GUARD["main"]([f"v{slen.__version__}"]) == 0


@pytest.mark.parametrize(
    ("tag", "project", "module", "refused"),
    [
        ("v0.4.0", "0.4.0", "0.4.0", 0),
        ("v0.4.1", "0.4.0", "0.4.0", 2),
        ("v0.4.0", "0.4.1", "0.4.0", 1),
        ("v0.4.0", "0.4.0", "0.4.1", 1),
        ("0.4.0", "0.4.0", "0.4.0", 2),
    ],
)
def test_a_tag_that_is_not_the_version_of_both_files_is_refused(
    tmp_path: Path, tag: str, project: str, module: str, refused: int
) -> None:
    assert len(GUARD["problems"](tag, tree(tmp_path, project, module))) == refused


def test_the_guard_wants_one_tag() -> None:
    assert GUARD["main"]([]) == 2


def test_the_release_builds_once_behind_the_guards_and_publishes_without_a_token() -> None:
    build, publish = WORKFLOW.split("\n  build:", 1)[1].split("\n  publish:", 1)

    assert "uses: ./.github/workflows/ci.yml" in WORKFLOW
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/master' in build
    assert "scripts/check_release.py" in build
    assert build.index("check_release.py") < build.index("uv build")
    assert "id-token: write" in publish
    assert "id-token" not in build
    assert "actions/checkout" not in publish
    assert "environment: { name: pypi" in publish
    assert "secrets." not in WORKFLOW
