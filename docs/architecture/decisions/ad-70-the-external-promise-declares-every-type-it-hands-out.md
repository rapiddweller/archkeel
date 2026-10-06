# AD-70 The external promise declares every type it hands out

## What changes

The original API exposed undeclared `Observation` and `ViolationFingerprint` types:

| Before | Type crossing the boundary | Declared? |
|---|---|---|
| `load_observation(path) -> Observation` | `ir.model.Observation` | no |
| `violation_rows(observation) -> tuple[ViolationRow, ...]` | `ir.model.Observation` | no |
| `ViolationRow.fingerprint` | `ir.baseline.ViolationFingerprint` | no |

Replace the composed calls with:

```python
from archkeel.api import load_violations

rows = load_violations(Path("architecture.json"))   # tuple[ViolationRow, ...]
```

`public_api` declares `ViolationFingerprint`, `ViolationRow` and `load_violations`.

## Why

AD-64 leaves `ir` free to change. Returning its `Observation` would promise that
model externally. Existing callers only composed load and row derivation; merge
them to remove the leaked model. Declare the fingerprint rather than duplicate
AD-52's rules and subjects on each row.

## Rejected

Declaring `Observation` promises internal IR. Keeping the old load function retains
the leak and two entry paths. Flattening fingerprints duplicates identity.

## Limit

Consumers needing other evidence have no entry yet; a future entry must declare
its types. The facade was unreleased after 0.4.x, so this breaks no published promise.
[AD-71](ad-71-a-promised-name-is-checked-against-the-modules-own-all.md) checks declared names.

## Check

Violation tests compare contract exports, verify fingerprint identity and load
typed rows with no intermediate `Observation` in the public call.
