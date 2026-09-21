# AD-68 `check` and `render` declare `boundary_types`, and the ten findings are declarations

## What changes

`CHECK-TYPES-DECLARED` and `RENDER-TYPES-DECLARED` join `ANALYZER-TYPES-DECLARED`. The three
types their facades expose are declared, not hidden and not carried as debt:

| Component | Type | Positions | Answer |
|---|---|---|---|
| `check` | `archkeel.check.ports:Analyzer` | 5 parameters: `observe_repository`, `run_report`, `run_check`, `run_init`, `run_validate` | declared, outer list and `foundation` inside |
| `check` | `archkeel.check.ports:Host` | 1 parameter: `run_check` | declared, both levels |
| `render` | `archkeel.render.summary:Summary` | 3 returns plus `print_result`'s parameter | declared |

No signature changed. No baseline was written.

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
| Change the signatures | Hides a Protocol the caller must implement behind an untyped parameter: a green rule bought by making the boundary less legible. |
| Carry the ten in a baseline ([AD-52](ad-52-a-violation-is-named-by-what-it-is-and-a-baseline-may-hold.md)) | Right when the architecture question is open. This one is not. |
| Teach `_drafted_public` to propose signature types | Needs the facade list it is still proposing, and a second scan. The guard change costs nothing and keeps its teeth. |

## Limit

Decides the ten positions that exist today, not the rule's reach. The collection-element reading
in flight (issue #59) adds two findings no declaration can answer: `run_init` and `run_validate`
both return `tuple[RunResult, dict[str, bytes]]`, and a bare `dict[...]` is the broad container
AD-58 names. That is a signature question, left open here. `api` declares no facade, so the rule
still does not reach it.

## Check

| Claim | Evidence |
|---|---|
| The declaration is legal now | `archkeel validate --root . --json` exits 0, no diagnostics; the same three entries before AD-65 gave exit 2 with `interface.unused` and `inside.public_mismatch` |
| Nothing is vacuous | `archkeel report` gives `declared_rules: PASS`, 0 violations, all three rules carrying subjects |
| The contract holds it, not a test | `tests/test_self.py::test_self_facades_record_the_ten_types_they_expose` reads both the entries and the rule sources from the contract |
