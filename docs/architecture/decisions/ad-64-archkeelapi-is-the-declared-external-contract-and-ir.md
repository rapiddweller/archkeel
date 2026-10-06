# AD-64 `archkeel.api` is the declared external contract, and `ir` performs no I/O

`archkeel.api` is the external read facade, initially exporting `ViolationRow`,
`load_observation` and `violation_rows` through `__all__`. Reference docs list the
same names; a test holds them equal. Move file reading from `ir.codec` to
`api.load_observation`, retaining the canonical decode/parse path.
Remove the days-old 0.4.x codec import path without a shim; old callers get ImportError.

`api` requires only `ir.baseline`, `ir.codec` and `ir.model` through its declared
boundary (AD-42). The new consumer pushes baseline usage over the half-of-names
threshold (AD-9); the self-contract follows the draft's whole-module public entry.

Issue #46 exposed AD-54's supported API existing only in prose and I/O inside
an evidence derivation. A top-level `api.py` is assigned and dependency-checked;
`archkeel/__init__.py` would be skipped as the scan namespace, hiding its crossings.
A second supported codec path would weaken the single external promise.

The no-I/O rule concerns derivations over already-read evidence (AD-17).
`ir/digest.py::package_digest` still reads installed Archkeel source for checker
identity; it is not consumer evidence derivation and is not externally exported.

Only the facade is promised externally. Internal codecs, columnar encoding and
component `public` entries remain separate, unpromised implementation boundaries.
Checks: `tests/test_violations.py` covers loading, reference exports, removed codec
imports and codec I/O; self tests cover draft parity, closed dependencies and validation.
