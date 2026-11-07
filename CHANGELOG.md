# Changelog

All notable changes to `slen` are written here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/), and before 1.0 a minor version may break.

## [Unreleased]

### Added
- `ExecutionCost.incomplete`: `True` when a provider billed something Slen could not price for one of the run's calls — a usage field it does not know, a price tier, a cache write or a server tool without a price — and `actual` is then what Slen knew. Set together with `actual`; `False` until then. The API always sends it, and an answer without it is an `InvalidResponseError`; `ExecutionCost(…)` takes it as a keyword.
- On `AttemptSummary`, the attempts of a trace node: `input_tokens` (the whole input, the cache read and writes included) and `output_tokens` (the whole paid output, reasoning included); `cached_input_tokens`, `cache_write_tokens`, `cache_write_long_tokens` and `reasoning_tokens`, the parts of those; `tool_calls`, the paid server-tool calls by name (`{"web_search": 6}`); `cost_breakdown`, an `AttemptCostBreakdown` — `input`, `cached_input`, `cache_write`, `output`, `tools` by name and `total`, decimal strings — `None` until the attempt is priced; `cost_incomplete`, the attempt's own `incomplete`. Each is `None` when the answer leaves it out, as the spec allows.
- On `FlowExecutionNode`, the nodes of a trace: `output` — what a model node left, its answer on `success` / `tool_calls` (`content`, `finish_reason`, `usage`, `tool_calls`, …) or its `error` on a failure port (`class`, `code`, `http_status`, `message`, `provider`, `model`, `retry_after_seconds`), as a dict; `output_truncated` — the kept output was cut to the limit (64 KB of JSON by default); `output_stored` — `"stored"`, `"disabled_by_project"` (the project keeps no model answers), `"withheld"` (grounded with Google Search: its `content` is not kept) or `"history_paused"`. `None` for every other node, and when the answer leaves them out — a trace of a backend that kept no outputs; `FlowExecutionNode(…)` takes them as optional keywords.
- `warnings` on `ExecutionResult`, `ExecutionStatusView` and `ExecutionTrace`: what the run said about its request when it started and went on with — a tuple of `ExecutionWarning` (`code`, `keys`, `message`; `keys` a tuple of strings or `None`), empty when there is nothing to say. `input_key_ignored`: the input carried keys of a model call (`tools`, `model`, `temperature`, …, named in `keys`) that no node of the flow passes to the model; the trace has the event `input_keys_ignored`. The API always sends it, and an answer without it is an `InvalidResponseError`; the three types take it as a keyword. Types only: the SDK does not log it yet.
- On `FlowExecutionNode`: `cost` is now the estimate the node's hold was taken on until the hold is captured, then what the provider billed — the sum of the call's attempts; `estimated_cost` keeps the estimate, `cost_status` says which of the two `cost` holds (`"estimated"`, `"actual"`), and `cost_incomplete` is `True` when the fact misses something the provider billed that Slen cannot price yet. The fact arrives up to a minute after the run ended. `None` when the answer leaves them out, as the spec allows; `FlowExecutionNode(…)` takes them as optional keywords.
- `pool_unavailable` (503) is in the contract copies, unmapped: a model node whose provider keys were all cooling down or refused. It leaves the node by its `unavailable` port; a run that ends on it carries it as its `error_code`, and as an HTTP error it falls back by status to `ProviderError`, like any 5xx without a row.

## [0.4.1] - 2026-11-02

### Added
- `PlanLimitError` (a `SlenError`): a refusal of the organization's plan. `plan_limit_reached` (409) — one more would pass what the plan allows — and `plan_feature_unavailable` (403) — the plan does not include the feature — become it; until now they fell back by status to `InvalidRequestError` and `AuthenticationError`. Its `details` carry `required_plan`, the plan to upgrade to. On the Free plan `customers.create()` of a new customer, `update_account()` and a `top_up()` that would open an account are refused so: end customers need a paid plan. No run is refused by a plan.
- `ExecutionTrace.history_paused`: the month's executions with history had run out when the run reached its first model call — it ran with the money fully protected and wrote no trace, so `nodes` and `events` are empty. `None` from a backend before 1.0.23.

## [0.4.0] - 2026-10-31

### Added
- The first release of the Python SDK — the surface of the PHP and TypeScript SDKs 0.4.0: `Slen` and `AsyncSlen`, runs and their wait, end customers, their credits and statements page after page, webhooks, the journal on the standard library's `logging`, spans and an OpenTelemetry bridge (`slen[otel]`), and `slen.testing` for your own tests.

[Unreleased]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Alexey-Shpilka/slen-python/releases/tag/v0.4.0
