# AD-68 `check` and `render` declare `boundary_types`, and the ten findings are declarations

## What changes

Adopt `CHECK-TYPES-DECLARED` and `RENDER-TYPES-DECLARED` beside the analyzer rule.
Declare the ten exposed positions:

| Component | Type | Positions | Answer |
|---|---|---|---|
| `check` | `archkeel.check.ports:Analyzer` | 5 parameters: `observe_repository`, `run_report`, `run_check`, `run_init`, `run_validate` | declared, outer list and `foundation` inside |
| `check` | `archkeel.check.ports:Host` | 1 parameter: `run_check` | declared, both levels |
| `render` | `archkeel.render.summary:Summary` | 3 returns plus `print_result`'s parameter | declared |

`run_init` and `run_validate` return `FilesToWrite`, a typed `Mapping[str, bytes]`,
replacing bare dicts while retaining callers' mapping operations. No baseline.

## Why

```python
def run_check(..., analyzer: Analyzer, host: Host) -> RunResult: ...
def check_summary(result: RunResult) -> Summary: ...
```

These types are required boundary contracts. `cli` passes values without importing
the names. [AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md) made
signature exposure count as usage, removing the declaration conflict that held
[AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md) to analyzer-only scope.
The self guard retains every inbound-import draft entry and allows extras only
when observation records prove facade exposure.

## Rejected

Bare dicts leave unnamed write containers. A baseline
([AD-52](ad-52-a-violation-is-named-by-what-it-is-and-a-baseline-may-hold.md)) would defer
an already decided declaration. Proposing exposed types during drafting needs
the facade list still being proposed and another scan.

## Current unknowns

At decision time, the self report recorded:

| Rule | Positions | Decided | UNKNOWN | Reasons |
|---|---:|---:|---:|---|
| `ANALYZER-TYPES-DECLARED` | 8 | 6 | 2 | 2 `external_type` |
| `RENDER-TYPES-DECLARED` | 27 | 24 | 3 | 3 `union` |
| `CHECK-TYPES-DECLARED` | 58 | 39 | 19 | 12 `union`, 6 `external_type`, 1 `generic` |

These limits report without gating. The report had zero violations and
`declared_rules: UNKNOWN`; validation exited 0 without diagnostics.

## Check

Onboarding and validation tests pin `FilesToWrite`; the report retains one limit
per nonvacuous rule. `test_self_facades_record_the_ten_types_they_expose` reads
contract entries and sources instead of hard-coded architecture policy.
