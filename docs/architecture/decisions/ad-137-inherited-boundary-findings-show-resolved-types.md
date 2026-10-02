# AD-137: Inherited boundary findings show resolved types

## Decision

Inherited `boundary_types` findings retain the source annotation and append the concrete
origins already proven by the substituted annotation verdict. `resolved_types` records those
origins as `module:Name` values. No second resolver or annotation rewrite is needed.

| Signature | Diagnostic evidence |
|---|---|
| `Base[T].get() -> T`, `Child(Base[Payload])` | Source `T`; resolved `module:Payload` |
| `Base[T].get() -> list[T]` | Source `list[T]`; the same concrete origin |
| Ambiguous substitution | Existing UNKNOWN; no invented origin |

## Why

A real missing declaration reported only as `T` sends the reviewer to the generic base
rather than the concrete model the contract must publish. The existing verdict already
holds that proof. Violation IDs, fingerprints, subjects and source evidence stay unchanged.

## Rejected and limits

Replacing `T` loses the source annotation; resolving it again duplicates the analyzer.
The origin list describes all proven types reached by the signature, including model fields;
it does not guess one offending origin from that list. Inheritance proof remains bounded by
AD-121. Direct findings keep their current wording.

## Verification

`tests/test_inherited_boundary_diagnostics.py` covers bare and collection substitutions,
raw annotations, stable IDs/fingerprints, declaring the model, ambiguous UNKNOWN, and
CLI/canonical/HTML output. The undeclared return and batch demos reproduce both findings;
the existing declared and ambiguous inherited demos remain the controls.
