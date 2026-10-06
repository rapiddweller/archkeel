# AD-65 A type a declared facade signature exposes is a used public entry

## What changes

A public entry is used by a cross-component import
([AD-9](ad-09-components-declare-their-interface.md),
[AD-56](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md)) or by a declared
facade signature.

```
check.public += archkeel.check.ports:Analyzer
$ archkeel validate --root .
exit 2   interface.unused | archkeel.check.ports:Analyzer     # before
exit 0                                                        # now
```

Only unused-entry checking changes; import boundaries and `boundary_types` stay
unchanged ([AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md)).

## Why

AD-63's ten check/render findings asked for types to be declared, but declaring
them produced `interface.unused`: consumers passed values without importing names.
The analyzer publishes resolved `facade_types` on function symbols; `check` reads
that key without importing the analyzer or repeating resolution.

Record it even without a boundary rule, allowing later adoption. The original
measurement found 64 facade functions exposing 26 types; five were undeclared,
including the three AD-63 findings and unowned `datetime.datetime`/`pathlib.Path`.
No diagnostic was suppressed. These counts are historical.

## Rejected

- A separate `exposed_types` list would duplicate public ownership and checks.
- Resolution in `check` would duplicate knowledge; in `ir` it would move evaluation
  and widen the analyzer boundary.
- Internal signatures/imports are not facade exposure; restricting to another
  component would miss the defining `run_report`/`Analyzer` case.

## Limit

Only bare names resolved initially; [AD-69](ad-69-one-annotation-is-read-once-for-both-readers.md)
closes generic exposure. No public means no facade types; planned entries do not
count. Exposure proves a promise, not an observed consumer. Analyzer version rises
to 0.28.0 (AD-3).

## Check

Analyzer and validation probes cover recorded facade types, used exposed entries
and unused internal-only types. The shop catalog retains unused findings for
unexposed types.
