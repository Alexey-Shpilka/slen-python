# Changelog

All notable changes to `slen` are written here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/), and before 1.0 a minor version may break.

## [Unreleased]

### Added
- `queue_slot`, a value of `WaitingOn.type`: the run waits for a slot of a Queue node's limit of calls at once. `execute()` answers such a run at once — `status` `waiting`, `retry_after_seconds` 2 — and the run goes on by itself when a slot is freed; `wait()` follows it as it follows any other wait. `resume_at` is the deadline: a run still without a slot then leaves by the node's `busy` port, and with nothing connected there it ends `rejected` with `error_code` `concurrency_limit_exceeded`. `type` stays a `str`; its comment names the value, and the README shows the wait.

### Changed
- `ConcurrencyLimitError` (`concurrency_limit_exceeded`, 402) is the refusal of a flow's Queue node whose limit of calls at once is full and whose `busy` port leads nowhere — no longer of a `concurrency` budget, a type the API no longer creates. Its `details` are the node's `busy` output: `reason` (`timeout`, `refused`, `queue_full`), `key`, `limit`, `in_flight`, `waiting`, `waited_seconds`. The docstring says so; the class and the code it maps are as they were.

## [0.5.0] - 2026-11-08

### Changed
- `FlowExecutionNode.cost` after the capture is the fact: the estimate the node's hold was taken on until the hold is captured, then what the provider billed — the sum of the call's attempts. `estimated_cost` keeps the estimate, `cost_status` says which of the two `cost` holds (`"estimated"`, `"actual"`), and `cost_incomplete` is `True` when the fact misses something the provider billed that Slen cannot price yet. The fact arrives up to a minute after the run ended. The three new fields are `None` when the answer leaves them out, as the spec allows; `FlowExecutionNode(…)` takes them as optional keywords.

### Added
- `warnings` on `ExecutionResult`, `ExecutionStatusView` and `ExecutionTrace`: what the run said about its request when it started and went on with — a tuple of `ExecutionWarning` (`code`, `keys`, `message`; `keys` a tuple of strings or `None`), empty when there is nothing to say. `input_key_ignored`: the input carried keys of a model call (`tools`, `model`, `temperature`, …, named in `keys`) that no node of the flow passes to the model; the trace has the event `input_keys_ignored`. The API always sends it, and an answer without it is an `InvalidResponseError`; the three types take it as a keyword. The SDK writes one that is not empty to the journal: `slen.execution.warnings` (in `LOG_EVENTS`) at the warning level, one record for each answer — `execute()`, `execute_async()`, `get()`, `trace()`, and the state a `wait()` answers with, on `Slen` and `AsyncSlen` — carrying the run's `execution_id` and each warning's `code` and `keys` (a list, or `None`), never its message.
- `ExecutionCost.incomplete`: `True` when a provider billed something Slen could not price for one of the run's calls — a usage field it does not know, a price tier, a cache write or a server tool without a price — and `actual` is then what Slen knew. Set together with `actual`; `False` until then. The API always sends it, and an answer without it is an `InvalidResponseError`; `ExecutionCost(…)` takes it as a keyword.
- On `AttemptSummary`, the attempts of a trace node: `input_tokens` (the whole input, the cache read and writes included) and `output_tokens` (the whole paid output, reasoning included); `cached_input_tokens`, `cache_write_tokens`, `cache_write_long_tokens` and `reasoning_tokens`, the parts of those; `tool_calls`, the paid server-tool calls by name (`{"web_search": 6}`); `cost_breakdown`, an `AttemptCostBreakdown` — `input`, `cached_input`, `cache_write`, `output`, `tools` by name and `total`, decimal strings — `None` until the attempt is priced; `cost_incomplete`, the attempt's own `incomplete`. Each is `None` when the answer leaves it out, as the spec allows.
- On `FlowExecutionNode`, the nodes of a trace: `output` — what a model node left, its answer on `success` / `tool_calls` (`content`, `finish_reason`, `usage`, `tool_calls`, …) or its `error` on a failure port (`class`, `code`, `http_status`, `message`, `provider`, `model`, `retry_after_seconds`), as a dict; `output_truncated` — the kept output was cut to the limit (64 KB of JSON by default); `output_stored` — `"stored"`, `"disabled_by_project"` (the project keeps no model answers), `"withheld"` (grounded with Google Search: its `content` is not kept) or `"history_paused"`. `None` for every other node, and when the answer leaves them out — a trace of a backend that kept no outputs; `FlowExecutionNode(…)` takes them as optional keywords.
- `model_retired` (403) becomes a `PolicyDeniedError`, as `model_not_allowed` does: a model its provider stopped listing, refused before any attempt — nothing was spent; the flow needs another model. Until now the API answered such a call with `model_not_allowed`; without the row the new code would fall back by status to `AuthenticationError`.
- `pool_unavailable` (503) is in the contract copies, unmapped: a model node whose provider keys were all cooling down or refused. It leaves the node by its `unavailable` port; a run that ends on it carries it as its `error_code`, and as an HTTP error it falls back by status to `ProviderError`, like any 5xx without a row.

## [0.4.1] - 2026-11-02

### Added
- `PlanLimitError` (a `SlenError`): a refusal of the organization's plan. `plan_limit_reached` (409) — one more would pass what the plan allows — and `plan_feature_unavailable` (403) — the plan does not include the feature — become it; until now they fell back by status to `InvalidRequestError` and `AuthenticationError`. Its `details` carry `required_plan`, the plan to upgrade to. On the Free plan `customers.create()` of a new customer, `update_account()` and a `top_up()` that would open an account are refused so: end customers need a paid plan. No run is refused by a plan.
- `ExecutionTrace.history_paused`: the month's executions with history had run out when the run reached its first model call — it ran with the money fully protected and wrote no trace, so `nodes` and `events` are empty. `None` from a backend before 1.0.23.

## [0.4.0] - 2026-10-31

### Added
- The first release of the Python SDK — the surface of the PHP and TypeScript SDKs 0.4.0: `Slen` and `AsyncSlen`, runs and their wait, end customers, their credits and statements page after page, webhooks, the journal on the standard library's `logging`, spans and an OpenTelemetry bridge (`slen[otel]`), and `slen.testing` for your own tests.

[Unreleased]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Alexey-Shpilka/slen-python/releases/tag/v0.4.0
