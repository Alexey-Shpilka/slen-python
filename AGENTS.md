# slen-python

## Purpose
`slen` — the Python SDK: `Slen` and `AsyncSlen` run flows and read their outcome, keep end customers and their credits, check webhooks, and write a journal and spans. The same surface as the PHP and TypeScript SDKs, call for call (`contract/calls.json`).

This repository is the package itself. `contract/` and the JSON of `examples/help/` are copies of the contract the SDKs share; the contract is kept, and every SDK is held against the API's OpenAPI spec, in the SDK's source repository.

## Key Files
| File | Description |
|------|-------------|
| `pyproject.toml` | `slen`, `requires-python >=3.11`, one dependency (`httpx>=0.27,<1`), the extra `otel`; hatchling builds it; the `dev` group pins the tools; ruff, mypy, pyright and pytest are configured here |
| `uv.lock` | the tools as CI installs them (`uv sync --locked`); the ranges of the package stay open |
| `src/slen/__init__.py` | the public surface (`__all__`), nothing else; `testing.py` (`FakeTransport`, `RecordedRequest`, `MemorySpanRecorder`) and `otel.py` (`OtelSpanRecorder`) are the two public submodules |
| `src/slen/_client.py`, `_config.py` | `Slen`, `AsyncSlen`: the options packed into `ClientOptions`, checked by `resolve_config()` — the one reader of the environment —, the chain and the modules built in `_build()`; `with_logger()`, `health()`, `close()` |
| `src/slen/_http/` | `_endpoints.py` (`Endpoint`, the operations of `calls.json`), `_request.py` (`ApiRequest`, the checks before the wire, the body's bytes), `_wire.py` (URL, headers, timeouts), `_retry.py`, `_journal.py`, `_error_map.py`, `_envelope.py` (the answer read), `_fields.py` (the strict reader of the wire), `_clock.py`, `_pool.py`, `_sync.py` / `_async.py` (one attempt and the loop of attempts) |
| `src/slen/_modules/<module>/` | `_types.py`, `_read.py` (the wire into the types), `_calls.py` (each call described once), `_sync.py` / `_async.py` (the two classes of the module); `executions/_wait.py` the state of a wait; `_pages.py` the loops; `webhooks/` the signature and the events |
| `src/slen/_observability/` | `SlenSpan`, `SpanScope`, the recorders |
| `tests/` | `support/` (paths, the harness, the spec and a schema check); a test per concern, `modules/` per module; `test_contract.py`, `test_help_examples.py`, `test_help_slice.py`, `test_readme.py`, `test_source_hygiene.py` |
| `examples/help/<id>/` | `python.py` (this package's code of the example) beside the copied `example.json` and `expect.json` |
| `help-slice.json`, `scripts/export_help_slice.py` | the help slice (schema 2) and what writes it (`--write`, `--check`, `--out`) |
| `scripts/floor.py`, `consumer.py`, `check_dist.py`, `check_release.py` | the installed wheel on the floor; the examples type-checked against it; what the wheel and the sdist hold; the guard of a tag |
| `.github/` | `workflows/ci.yml` (no secrets), `workflows/release.yml` (a tag → PyPI, no token), `dependabot.yml`, `AGENTS.md` |

## Commands
```bash
# The toolchain runs in a container, from the root of this repository, with the environment in a volume.
docker run --rm -v "$PWD":/pkg -v slen-venv:/venv -w /pkg -e UV_PROJECT_ENVIRONMENT=/venv python:3.11-slim \
  sh -c 'pip install --quiet uv==0.13.6 && uv sync --locked --all-extras --inexact'
docker run --rm --network none -v "$PWD":/pkg:ro -v slen-venv:/venv:ro -w /pkg -e PYTHONDONTWRITEBYTECODE=1 \
  -e PATH=/venv/bin:/usr/local/bin:/usr/bin:/bin python:3.11-slim \
  sh -c 'ruff check --no-cache . && ruff format --no-cache --check . && mypy --cache-dir /tmp/mypy && pyright && pytest -p no:cacheprovider'
# against the API's spec: add -v <dir of the spec>:/spec:ro -e SLEN_OPENAPI_SPEC=/spec/v1.yaml
# the slice: python scripts/export_help_slice.py --check (or --write after a change of the surface)
# what ships (needs the index): uv build -o /tmp/dist && twine check --strict /tmp/dist/* \
#   && python scripts/check_dist.py /tmp/dist && python scripts/consumer.py /tmp/dist
```

## Releasing
A release is an annotated tag `vX.Y.Z` on `master`; `.github/workflows/release.yml` publishes it to PyPI by trusted publishing (OIDC), with attestations. No PyPI token exists, here or in the repository's secrets.
1. On a branch named for the version (`release/X.Y.Z`): `version` of `pyproject.toml`, `__version__` of `src/slen/_version.py`, `python scripts/export_help_slice.py --write` (the slice carries the version), the Compatibility table of the README, and in `CHANGELOG.md` what `## [Unreleased]` gathered becomes `## [X.Y.Z] - YYYY-MM-DD` under a new, empty `## [Unreleased]`, the links at the bottom following. Every PR writes its line under `[Unreleased]` as it lands.
2. A pull request, green, merged to `master` with a merge commit.
3. On that commit of `master`: `git tag -a vX.Y.Z -m "slen-python X.Y.Z"`, then `git push origin vX.Y.Z`.
4. `release.yml` runs the gates of `ci.yml` on the tag's commit; `build` refuses a tag whose commit is not on `master` a tag that is not `v` + the version of `pyproject.toml` and of `slen.__version__`, and a version with no dated section and link in `CHANGELOG.md` (`scripts/check_release.py`), then builds the wheel and the sdist once and checks them (`twine check --strict`, `check_dist.py`); `publish` uploads exactly those files.
5. **PyPI never takes a file name twice**, not even after a delete: a failed run whose cause passes (PyPI down) is a re-run of the same run; a fault in the tree is a new version. A pushed tag is never moved or deleted; a broken release is yanked on pypi.org, never replaced.

**Once, by the owner, on the day of the first tag**: GitHub → Settings → Environments → `pypi`, deployment rule for tags `v*`; pypi.org → Publishing → a pending publisher for the project `slen`: owner `Alexey-Shpilka`, repository `slen-python`, workflow `release.yml`, environment `pypi` — and check that it is listed, since a pending publisher reserves no name. Should PyPI refuse `slen` as too close to a name it has, the distribution becomes `slen-sdk` (a new pending publisher under that name); the import stays `slen`.

## House rules
The rules of the house, as this package keeps them; each is held by a test.

| Rule | Here |
|---|---|
| strict types everywhere | annotations on everything, mypy `--strict` and pyright `strict`; no `Any` in a public signature but the JSON of a flow |
| at most three arguments, more travel in an object | at most three positional parameters everywhere; the keyword options of a public call and the constructors of dataclasses are the written exception; a function that is not public takes at most three parameters in all, and a call packs its options into one immutable object at once |
| at most three dependencies of a constructor | the same |
| an early return, no nested `if`, a complex condition in a function | the same; no `else`, no `elif`, no `else` of a loop or a `try`; `x if c else y` is allowed in `src/`, not in an example |
| explicit comparisons | not carried over: `if run.is_completed():` is Python's idiom; `None` only with `is None` / `is not None` |
| one return type | the same; `T \| None` where `None` means something |
| no static state | no `@staticmethod`, no state of a module that can change (a module keeps `Final` values, tuples, `frozenset`, `MappingProxyType`, frozen dataclasses) |
| a docblock is tags only | a public symbol and method carry a docstring of one line (what a caller's editor shows); nothing internal carries one; the reasons live here |
| no `DTO`, `Service` suffixes | not carried over: what is internal lives in modules named `_…`; the public types are named as the spec and the other SDKs name them |
| enums of strings, snake_case values | `StrEnum`, members in `UPPER_CASE`, values as the wire spells them |
| money is never a float | the same: credits and money are `str` |

## For AI Agents
- **The gate** is ruff (check and format), mypy (and mypy on each example), pyright, pytest and the slice `--check`, on Python 3.11 and 3.14 and on httpx 0.27, in containers (`--network none` once the environment is installed). `pyright --verifytypes slen --ignoreexternal` is 100 %.
- **Two clients, one core.** A call is described once (`_modules/*/_calls.py`: an `ApiRequest` and the reader of its answer); `_sync.py` and `_async.py` only send it. `tests/test_twins.py` holds every public method of `Slen` to one of `AsyncSlen` with the same signature; a new call is written in both in the same commit.
- **The environment is `SLEN_API_KEY`, read in `_config.py` alone.** The address is `DEFAULT_BASE_URL` (`https://api.slen.ai`, `servers[0]` of the spec); `base_url` is for tests and a local stack, never in the README or an example.
- **A request is an `Endpoint` and values**: the journal and every message name the route template, never a value of the path or the query. No other literal of `src/` spells a path (`tests/test_contract.py`).
- **Refused before the wire** with `InvalidRequestError` (`invalid_request`), nothing sent and no span: a blank path value or idempotency key, a body that is not JSON, credits of the wrong form, a `customer` other than `context["user_id"]`, a call's `timeout` not above 0, `retries` not an integer ≥ 0, a `request_id` that is not 8 to 128 of `A-Z a-z 0-9 . _ : -`. A client built with a wrong option is a `TypeError` or a `ValueError`.
- **The body's bytes are the SDK's** (`json.dumps(…, separators=(",", ":"), ensure_ascii=False)` into `content=`), the same on httpx 0.27 and 0.28: the server hashes them under the idempotency key.
- **Every request carries the SDK's timeout** (`timeout=` of httpx), so a client of the user's built without one is not cut at httpx's five seconds. `AsyncSlen` holds an attempt to one deadline (`asyncio.timeout`); `Slen` runs on httpx's clocks by phase and checks the deadline between the chunks of the body. A body that stalls is a `TimeoutError`, a wire that failed a `ConnectionError`; neither has a code (`tests/test_timeout.py`, on a real socket).
- **Retry**: no answer, 429 and any 503, under the same idempotency key; `Retry-After` up to 30 s is waited out, without it 200 ms × 2ⁿ ±25 %, at most 5 s. 500, 502, 504 are never repeated. A cancelled task is never repeated and never swallowed.
- **Answers are read strictly** (`_http/_fields.py`): a field the spec requires that is missing, null or of another type, or a status the SDK does not know, is `InvalidResponseError` with the status, the field named, the body never quoted. A field the spec may leave out is `None` when it is. `request_id` is the last field of every answer of a call, `compare=False`.
- **The journal** is stdlib logging, the `slen` logger (a `NullHandler`) unless one is given; the event is the message, its fields are `extra` — none of them an attribute of `LogRecord`. Never written: the key, `Authorization`, the webhook secret, the idempotency key, bodies, the server's `error.message`, values of the path or the query (`tests/test_journal.py`). A logger or a recorder that raises is swallowed.
- **A client cannot be pickled or copied** (`__reduce__` raises `TypeError`); its key is in no `repr`. `with_logger()` is the copy: the same connections and recorder, no ownership of the pool.
- **Comments in `src/`**: six lines at most, no history, no plan numbers; comment and docstring lines are at most a tenth of `src/` (`tests/test_source_hygiene.py`).
- **Nothing internal in any file of the package**: no path of a machine, plan or its numbers, private repository, local stack, earlier name of the product or real-looking key; a guard spells its own patterns with character classes.
- **The floor is Python 3.11**: no syntax of 3.12, no `typing.override`, no `typing_extensions` — it is not a dependency.

## Help examples
`examples/help/<id>/python.py` is code the console's Help & Docs prints: an article shows a region of it, never code of its own. `tests/test_help_examples.py` runs each file as it is (`runpy`), with the harness's key in `SLEN_API_KEY`, the SDK's own HTTP client (`_http/_pool.py`) answering from `responses` and the clock (`_http/_clock.py`) moved by the waits; what it sent is held against `calls` of `expect.json`, what it printed against `prints`.
- **Regions** are the lines between `# docs:start <name>` and `# docs:end`, exactly those `example.json` lists, in order; what a reader does not see stays outside, after a `# Harness:` comment, and no region reads a name only such a line binds.
- **An example** shows the SDK without an address, keys as `sl_live_…`, an idempotency key derived from the unit of work, no `else` in any form (no `elif`, no conditional expression), `run.output` read after it is not `None`; it type-checks under mypy `--strict` and pyright strict against the installed package (`scripts/consumer.py`).
- **A framework example** (`framework` in `example.json`) is an application: FastAPI under `TestClient`, its lifespan run; Django under `django.test.Client`, configured by the harness. The client is built where a worker builds it — the lifespan, the first request — never on import.
- **With the spec** every answer an example is served and every body it sends is held against the schema of its operation, for every example in the tree.
