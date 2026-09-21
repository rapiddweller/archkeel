# AD-67 An undecidable boundary position is UNKNOWN, not silence

## What changes

`boundary_types` wrote a record only for a violation, so a decided pass and six kinds of
undecidable position were all `None`: the rule read `no violation == probably fine` where the
tool elsewhere reads PASS, VIOLATION, UNKNOWN. Two steps, one commit each:

1. `_boundary_type_verdict` answers a violation, an undecidable kind, or a decided pass, and one
   `boundary_type_limit` record per rule reports positions seen, decided, undecided and the count
   per kind. Same shape as `dynamic_call_limit`.
2. `_collection_verdict` decides `Container[Name]` for the known collections by running that same
   verdict on each parameter, one level in (`enter_collections=False` keeps it there).

## Measured, 258 positions in 88 facade functions

| | main | step 1 | step 2 |
|---|---:|---:|---:|
| violation | 36 | 36 | 39 |
| decided pass | 153, silent | 153 | 181 |
| undecidable | 69 (27%) | 69 | **38 (15%)** |

By kind: generic 41→9, union 17→18, external 10→10, unresolved name 1→1.

The issue's 146 does not survive: 79 are builtins, which issue #9 names acceptable. They only
looked unresolvable because a builtin defines no symbol. Honest remainder before step 2: 69.

Step 2's three new findings are all the wrapping hole, none false: `ir.levels.inside_levels`
returns `tuple[InsideLevel, ...]`, and `check.onboarding.run_init` and
`check.validation.run_validate` both return `tuple[RunResult, dict[str, bytes]]`.

## Why report, not gate

```python
def execute(context: InternalContext) -> Result: ...         # reported
def execute(contexts: list[InternalContext]) -> Result: ...  # silent before step 2
```

The record goes to `unknowns`, never `coverage.failures`; exit code, `coverage.rules` and
diagnostics do not move. A rule that decides nothing is already gated by AD-63. Gating the rest
would fail this repository on 41 tuples and 10 `Path` parameters, none of them a finding, and a
gate nobody can clear by declaring anything gets deleted.

## Rejected

| Alternative | Why not |
|---|---|
| One UNKNOWN per undecidable position | 146 rows on one repository is the section-skipping AD-26 names. A reader needs size and kind, not identity. |
| A field on `Coverage` | `Coverage` speaks about the scan and is computed before rules run. How much one rule decided belongs to that rule. |
| Counting undecidable as a violation | Guessing is worse than silence (AD-63's Limit). This only makes the silence say how large it is. |
| Descending recursively | A nested subscript is a second question. 31 of 41 undecided generics are one level deep. |
| Entering `Mapping[...]` | Raises AD-58's broad-container question, which this does not answer. |

## Limit

The record says how many of each kind, not which ones. Unions, mappings, nested subscripts,
dotted names, forward references and unowned types stay undecidable: 38 of 258 here.
`_BUILTIN_NAMES` is the running interpreter's, so two Python builds can classify differently; the
analyzer digest (AD-3) keeps such runs apart. `ANALYZER_VERSION` rises twice, 0.28.0 and 0.29.0.

## Check

| Test | Red on |
|---|---|
| `test_boundary_types_reports_a_position_it_could_not_decide` | pre-fix code: no limit record at all |
| `test_boundary_types_decides_a_bare_name_inside_a_collection` | step-one code: wrapped `list[Payload]` silent |
| demo row `class-a-boundary-types-in-collection` | regenerated into `docs/architecture-demo.md` |

`archkeel validate --root . --json` still exits 0, with `ANALYZER-TYPES-DECLARED` now saying how
much of `analyzer`'s facade it decided.
