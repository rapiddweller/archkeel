# AD-68 `check` and `render` declare `boundary_types`, and the ten findings are declarations

## What changes

`CHECK-TYPES-DECLARED` and `RENDER-TYPES-DECLARED` join `ANALYZER-TYPES-DECLARED`. The three
types their facades expose are declared, not hidden and not carried as debt:

| Component | Type | Positions | Answer |
|---|---|---|---|
| `check` | `archkeel.check.ports:Analyzer` | 5 parameters: `observe_repository`, `run_report`, `run_check`, `run_init`, `run_validate` | declared, outer list and `foundation` inside |
| `check` | `archkeel.check.ports:Host` | 1 parameter: `run_check` | declared, both levels |
| `render` | `archkeel.render.summary:Summary` | 3 returns plus `print_result`'s parameter | declared |

`run_init` and `run_validate` now return `FilesToWrite`, a typed `Mapping[str, bytes]` port,
instead of a bare `dict[str, bytes]`. Existing callers keep the same mapping operations. No
baseline was written.

## Why

A caller cannot call `run_check` without satisfying `Host`, and cannot use what `check_summary`
returns without `Summary`. The type is the contract, not something behind it:

```python
def run_check(..., analyzer: Analyzer, host: Host) -> RunResult: ...
def check_summary(result: RunResult) -> Summary: ...
```

`cli` writes none of the three names — it passes values in and hands results on — which is why
declaring them was impossible before [AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md)
made a facade signature a second way of reaching an entry. Until then the declaration produced
`interface.unused` and `inside.public_mismatch`, and that, not judgement, is why
[AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md) adopted the rule
for `analyzer` alone.

The AD-9 guard that `public` comes from `draft_contract` had to learn the same second reading:
`_drafted_public` proposes from inbound imports only, so it never proposes a type nobody imports.
The guard now checks both readings — no proposed entry may be edited away, and every extra entry
must be one the observation records a facade signature as exposing.

## Rejected

| Alternative | Why not |
|---|---|
| Keep the bare `dict[str, bytes]` returns | Leaves the write result as an unnamed broad container. `FilesToWrite` makes the boundary explicit while preserving mapping behavior. |
| Carry the ten in a baseline ([AD-52](ad-52-a-violation-is-named-by-what-it-is-and-a-baseline-may-hold.md)) | Right when the architecture question is open. This one is not. |
| Teach `_drafted_public` to propose signature types | Needs the facade list it is still proposing, and a second scan. The guard change costs nothing and keeps its teeth. |

## Current unknowns

The collection-element case from issue #59 is resolved by `FilesToWrite`; `run_init` and
`run_validate` no longer expose `dict[str, bytes]`. The self report still records checker limits,
one UNKNOWN record per declared rule:

| Rule | Positions | Decided | UNKNOWN | Reasons |
|---|---:|---:|---:|---|
| `ANALYZER-TYPES-DECLARED` | 8 | 6 | 2 | 2 `external_type` |
| `RENDER-TYPES-DECLARED` | 27 | 24 | 3 | 3 `union` |
| `CHECK-TYPES-DECLARED` | 58 | 39 | 19 | 12 `union`, 6 `external_type`, 1 `generic` |

These records report and do not gate. The current self report has 0 violations and
`declared_rules: UNKNOWN`; `validate --root . --json` exits 0 with no diagnostics.

## Check

| Claim | Evidence |
|---|---|
| The declaration is legal now | `archkeel validate --root . --json` exits 0 with no diagnostics; `tests/test_onboarding.py::test_run_init_declares_a_files_type_that_is_not_a_bare_dict` and `tests/test_validation.py::test_run_validate_declares_a_files_type_that_is_not_a_bare_dict` pin the typed write result |
| Unknowns stay explicit | `archkeel report` records one `boundary_type_limit` per rule with the counts above; `declared_rules` is `UNKNOWN`, not `PASS` |
| Nothing is vacuous | The same report has 0 violations and all three rules carry subjects |
| The contract holds it, not a test | `tests/test_self.py::test_self_facades_record_the_ten_types_they_expose` reads the entries and rule sources from the contract |
