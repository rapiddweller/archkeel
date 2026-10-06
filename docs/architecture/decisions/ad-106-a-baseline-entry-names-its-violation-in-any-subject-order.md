# AD-106: A baseline entry names its violation in any subject order

A violation's fingerprint (AD-52) uses sorted rule ids and subjects.
`canonical_fingerprint` constructs both observation and baseline fingerprints:

```python
def canonical_fingerprint(rules: Iterable[str], subjects: Iterable[str]) -> ViolationFingerprint:
    return ViolationFingerprint(tuple(sorted(rules)), tuple(sorted(subjects)))
```

A refused `--write-baseline` (AD-77) ends `failures` with this line, after widening or narrowing.
No line in that run advises `--write-baseline`:

```
--write-baseline refused: writing would accept the new or increased debt above; fix the code, or add --accept-new once an architect has decided to accept it
```

An existing baseline that cannot be read is `baseline.invalid` with the remedy "Correct the
baseline file by hand": a write reads the file first and stops on the same error. Only a
missing file, which a write creates, is pointed at `--write-baseline`.

## Why

Issue #152. The analyzer writes `subjects` sorted, but the reader kept the order it found. A
namespace renamed by text replace (`window_cleaning_mobile` to `field_service_mobile`) sorts
differently next to `flutter_stripe.…`, so every renamed entry became one new and one resolved
violation, exit 1. The subjects carry no direction; the `roles` of schema 1.1 do (AD-78).

The refused run then printed `rewrite the baseline with --write-baseline` beside each resolved
entry, advising the command that had just refused.

| Case, measured on the sample (`docs/architecture-demo.md`) | before | after |
|---|---|---|
| `baseline.subject_order`: Money import, subjects reversed | exit 1, new 1, resolved 1 | exit 0, no drift |
| `baseline.refused`: last `failures` line | advises `--write-baseline` | says refused, names `--accept-new` |

## Rejected

- **Match subjects as a set.** `["a", "a"]` and `["a"]` would be one violation. A sorted tuple
  keeps every subject.
- **Sort only in the reader.** An observation read from disk is not re-sorted by `classified`,
  so both sides go through one function.
- **Sort in `ViolationFingerprint.__post_init__`.** A frozen dataclass needs `object.__setattr__`
  for that, which Archkeel's own scan counts as two unresolved calls (`calls_unresolved`
  502 -> 504).
- **Sum two entries that differ only in order.** The file states one violation twice; it stays
  `baseline.invalid`, exit 2, naming both entries and the violation (`rules | subjects`), rather
  than a count that could hide a second occurrence.

## Limit

The file format does not change: the writer already wrote sorted lists, and a rewrite sorts an
entry read in another order. Two directions of one pair under one rule were one fingerprint
before and still are; the count keeps both visible, and `--against` still rejects a role change
(AD-90).

## Check

`tests/test_baseline.py` covers sorting, multiplicity, duplicate rejection, directional roles
and refusal ordering, including `--against` widening. `tests/test_measurement_budgets.py` covers
budget lines. `tests/test_architecture_demo.py` runs both catalog rows.
