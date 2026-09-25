# AD-106: A baseline entry names its violation in any subject order

A violation's fingerprint (AD-52) is its sorted rule ids and its sorted subjects, whatever order
they arrive in. `canonical_fingerprint` is the one place both a violation record and a baseline
entry become a fingerprint:

```python
def canonical_fingerprint(rules: Iterable[str], subjects: Iterable[str]) -> ViolationFingerprint:
    return ViolationFingerprint(tuple(sorted(rules)), tuple(sorted(subjects)))
```

A `--write-baseline` that refuses new or increased debt (AD-77) ends its `failures` with one line
that says so, and no line of that run advises `--write-baseline`:

```
--write-baseline refused: writing would accept the new or increased debt above; fix the code, or add --accept-new once an architect has decided to accept it
```

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
- **Sum two entries that differ only in order.** The file states one violation twice; it stays
  `baseline.invalid` ("repeats a fingerprint"), exit 2, rather than a count that could hide a
  second occurrence.

## Limit

The file format does not change: the writer already wrote sorted lists, and a rewrite sorts an
entry read in another order. Two directions of one pair under one rule were one fingerprint
before and still are; the count keeps both visible, and `--against` still rejects a role change
(AD-90).

## Check

`tests/test_baseline.py`: a reversed entry passes and is written back sorted; a repeated subject
still counts; two entries differing only in order are rejected; a reversed entry for `a -> b`
does not absorb `b -> a`, and a role change still widens; a refused run names the new and the
resolved entry without advice, then the refusal. `tests/test_measurement_budgets.py` covers the
budget lines. `tests/test_architecture_demo.py` runs the two catalog rows.
