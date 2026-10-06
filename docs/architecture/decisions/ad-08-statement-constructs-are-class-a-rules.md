# AD-8 Statement constructs are Class A rules

`forbidden_construct` adds `assert`, `broad_except` and optional prefix-scoped
`allowed_sources`, as in `external_dependency_scope`. A broad handler catches
`Exception` or `BaseException`, including bare handlers, tuples and
`builtins.Exception`. Re-raising still counts; intent belongs to review, and a
justified boundary belongs in `allowed_sources`. Aliases and shadowing remain blind spots.

Records use `constructs`; putting them in `typing_signals` would incorrectly count
them as typing positions. Contract `schema_version` stays 2.0.0: the wider enum and
optional key invalidate no existing contract. Older versions reject them with exit 2.

These are observation facts, so they are Class A rules. Check: one violation probe
per construct in `tests/test_analyzer.py`; the self-contract forbids both and allows
only the CLI broad-handler boundary.
