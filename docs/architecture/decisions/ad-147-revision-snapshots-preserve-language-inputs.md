# AD-147 Revision snapshots preserve language inputs

A check reads the selected revision's source and resolver metadata as exact Git blobs.
Archive attributes cannot remove or rewrite that evidence. Extraction still rejects unsafe
paths, duplicate members and links.

The IR component publishes only `identity:module_identity` for TypeScript source naming. The
analyzer's `requires.through` admits that module; its helpers remain private. TypeScript IDs
preserve path distinctions. Dart retains its existing IDs and marks colliding planned and
observed paths UNKNOWN, so a differently spelled file cannot satisfy a target.

Dart records the directive parser and its actual Python runtime. Missing or unknown analyzer,
contract, producer and runtime identities cannot establish comparison by equality. A null legacy
Python version alias remains readable; it supplies no runtime proof. The shared observation schema
admits each supported profile; the Python wrapper continues to require Python arrays.

Analyzer version becomes `0.67.0`; shared source identity does not widen its public helpers.
The own unresolved-call ceiling becomes 597 (567 + 33 added - 3 removed), following source-level
review of required blob, archive and path checks. All other ceilings remain unchanged.

Checks: `tests/test_snapshot.py`, `tests/test_dart_profile.py`, `tests/test_runtime_delta.py`,
`tests/test_schema_drift.py`; `make demo-snapshot-check` runs committed Python and Dart controls.
