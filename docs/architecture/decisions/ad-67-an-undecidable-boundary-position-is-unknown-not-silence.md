# AD-67 An undecidable boundary position is UNKNOWN, not silence

## What changes

`_boundary_type_verdict` distinguishes violation, decided pass and undecidable
positions. One `boundary_type_limit` per rule counts seen, decided and undecided
positions by kind. `_collection_verdict` then applies the same walk one level
inside known collections, with `enter_collections=False` preventing recursion.

## Measured, 258 positions in 88 facade functions

| | main | step 1 | step 2 |
|---|---:|---:|---:|
| violation | 36 | 36 | 39 |
| decided pass | 153, silent | 153 | 181 |
| undecidable | 69 (27%) | 69 | **38 (15%)** |

Kinds changed: generic 41→9, union 17→18, external 10→10, unresolved name 1→1.
The issue's 146 included 79 acceptable builtins; the actual initial remainder was 69.
Three new findings exposed wrappers: `tuple[InsideLevel, ...]` and two
`tuple[RunResult, dict[str, bytes]]` returns.

## Why report, not gate

```python
def execute(context: InternalContext) -> Result: ...         # reported
def execute(contexts: list[InternalContext]) -> Result: ...  # silent before step 2
```

Limit records go to `unknowns`, not coverage failures. Exit code, coverage and
diagnostics stay unchanged; AD-63 already gates zero-subject rules. Gating all
uncertainty would require clearing undecidable tuples and external `Path` types.

## Rejected

Per-position UNKNOWN rows would overwhelm review. Coverage is scan evidence,
not rule-level resolution. Uncertainty is not a violation. Recursive subscripts
and mappings require separate decisions beyond this one-level collection cut.

## Limit

Counts identify no positions. Unions, mappings, nested subscripts, dotted names,
forward references and unowned types remain undecidable: 38/258 here.
`_BUILTIN_NAMES` depends on the interpreter; AD-3 comparability separates builds.
Analyzer versions rose to 0.28.0 and 0.29.0.

## Check

Analyzer tests cover explicit undecidable limits and collection elements;
`class-a-boundary-types-in-collection` demonstrates the wrapping finding.
Self validation still exited 0 with the analyzer rule's decision counts visible.
