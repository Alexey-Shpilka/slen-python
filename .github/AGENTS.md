# .github

## Purpose
The CI and the release of `slen`. No job reads a secret: a pull request from a fork runs exactly what a push to `master` runs, and a tag is published without a PyPI token.

## Key Files
| File | Description |
|------|-------------|
| `workflows/ci.yml` | `python` (3.11, 3.12, 3.13, 3.14: `uv sync --locked`, ruff check and format, mypy and mypy on each example, pyright, pytest, the help slice `--check`), `python-lowest` (3.11 with every direct dependency at its lowest, the check that httpx 0.27 is what got installed, pytest, then the wheel installed in place of the source and `scripts/floor.py`), `python-consumer` (the build, `twine check --strict`, `scripts/check_dist.py`, `scripts/consumer.py`), `python-newest` (weekly and by hand: every dependency at its newest, pytest); also `workflow_call`, for the release |
| `workflows/release.yml` | on a pushed tag `v*`: `gates` (`ci.yml`, called) on the tag's commit; `build` — the tag checked against `master`, the version and its dated section of `CHANGELOG.md`, the wheel and the sdist built once and checked, kept as an artifact; `publish` — those files to PyPI by trusted publishing |
| `dependabot.yml` | weekly: the pinned actions, and the tools of `uv.lock`; minors and patches in one PR per ecosystem, the majors of `httpx`, `pytest`, `mypy` and `pyright` ignored — they change what the suite holds, so they are taken by hand, in a change of their own |

## For AI Agents
- **Every action is pinned to a commit**, with its version in a comment; Dependabot moves both. `permissions: contents: read`, plus `id-token: write` on `publish` alone; every checkout is `persist-credentials: false`.
- **No secret, no other repository.** The checks that need the API's OpenAPI spec skip without `SLEN_OPENAPI_SPEC`; they run with the spec where the contract is kept, against this repository's tags and `master`.
- **The Python is setup-python's** (`UV_PYTHON_DOWNLOADS: never`), uv is the version the job names, and `uv sync --locked` installs the tools exactly as `uv.lock` has them: a lock that does not match `pyproject.toml` fails the job.
- **The lowest leg checks what it got**: without the step that asserts httpx 0.27, a resolver that picked a newer one would make it pass for nothing. The floor runs on the installed wheel, so a module missing from the wheel or a missing `py.typed` is red there.
- **A release builds once**: `build` makes the files and `publish` uploads them unchanged; PyPI never takes a file name twice, so a release is never rebuilt — a passing failure is a re-run of the same run, a fault in the tree a new version.
- **Nothing of the repository runs beside the token**: `publish` has no checkout and no cache, only the artifact of `build` and `pypa/gh-action-pypi-publish`, which writes the attestations by default.
- **`release.yml` keeps its name and the environment `pypi`**: the trusted publisher on pypi.org names both; under another name PyPI refuses the upload until the publisher names the new one.
- **One release at a time** (`concurrency: release`, never cancelled in progress).
