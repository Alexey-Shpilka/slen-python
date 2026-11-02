# Changelog

All notable changes to `slen` are written here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/), and before 1.0 a minor version may break.

## [Unreleased]

## [0.4.1] - 2026-11-02

### Added
- `PlanLimitError` (a `SlenError`): a refusal of the organization's plan. `plan_limit_reached` (409) — one more would pass what the plan allows — and `plan_feature_unavailable` (403) — the plan does not include the feature — become it; until now they fell back by status to `InvalidRequestError` and `AuthenticationError`. Its `details` carry `required_plan`, the plan to upgrade to. On the Free plan `customers.create()` of a new customer, `update_account()` and a `top_up()` that would open an account are refused so: end customers need a paid plan. No run is refused by a plan.

## [0.4.0] - 2026-10-31

### Added
- The first release of the Python SDK — the surface of the PHP and TypeScript SDKs 0.4.0: `Slen` and `AsyncSlen`, runs and their wait, end customers, their credits and statements page after page, webhooks, the journal on the standard library's `logging`, spans and an OpenTelemetry bridge (`slen[otel]`), and `slen.testing` for your own tests.

[Unreleased]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Alexey-Shpilka/slen-python/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Alexey-Shpilka/slen-python/releases/tag/v0.4.0
