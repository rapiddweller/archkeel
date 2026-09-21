# AD-70 The external promise declares every type it hands out

## What changes

`archkeel.api` promised three names and handed out two types it never declared:

| Before | Type crossing the boundary | Declared? |
|---|---|---|
| `load_observation(path) -> Observation` | `ir.model.Observation` | no |
| `violation_rows(observation) -> tuple[ViolationRow, ...]` | `ir.model.Observation` | no |
| `ViolationRow.fingerprint` | `ir.baseline.ViolationFingerprint` | no |

The surface is now one call and three declared names:

```python
from archkeel.api import load_violations

rows = load_violations(Path("architecture.json"))   # tuple[ViolationRow, ...]
```

`public_api` declares `ViolationFingerprint`, `ViolationRow` and `load_violations`.

## Why

AD-64 promises `archkeel.api` stays stable while `ir` is free to change. A facade returning
`ir`'s own `Observation` promises the whole model instead, which is the leak `boundary_types`
reports inside this repository (AD-58, AD-63): a declared facade must not hand out a type no
one declared. The external surface was held to a weaker standard than any internal component.

The two functions only ever composed: nobody called `violation_rows` on an `Observation` they
did not just load. Collapsing them removes the `Observation` from the boundary entirely rather
than declaring it, which would have promised `ir.model` to consumers forever.

`ViolationFingerprint` is declared rather than flattened into the row, because AD-52's row
deliberately carries no second copy of `rules` and `subjects` -- one place to drift, not two.

## Rejected

| Alternative | Why not |
|---|---|
| Re-export and declare `Observation` | Promises `ir`'s whole model externally, the opposite of what AD-64 bought. |
| Keep `load_observation` beside `load_violations` | Two supported ways in, one of them the leak. |
| Copy `rules`/`subjects` onto the row | Two places for one identity to drift (AD-52). |

## Limit

A consumer who wants more than violations has no entry now; adding one later is cheap, and it
would carry its own declared types. This is free today because `archkeel.api` is unreleased:
it arrived after 0.4.x, so no published promise is broken. Whether `public_api` should also
check that the declared *symbol* exists, not just its module, is issue #58's remaining half.

## Check

`tests/test_violations.py::test_api_all_matches_the_names_reference_md_documents` reads the
three names from the contract and asserts `archkeel.api.ViolationFingerprint` is the type
`row.fingerprint` hands out; `test_load_violations_reads_the_canonical_report_bytes_back`
proves the one call returns typed rows with no `Observation` in between.
