# AD-47 `init` breaks a tie between top-level packages with `pyproject.toml`'s `[project] name`, and with nothing else

`detect_source` selects the sole top-level package under `src/`, or under the root
when `src/` is absent. For multiple packages, normalize root `pyproject.toml`'s
`[project] name` to wheel form: lowercase and replace runs of `-`, `_` or `.` with `_`.
Select exactly one package with the same lowercased directory name.

Missing/unreadable TOML or name, and zero or multiple matches, retain exit 2,
`scope_empty` and the `--source`/`--namespace` remedy. The diagnostic names the
compared project name or `missing`. A sole package still needs no name comparison.

DATAMIMIC CE 0.4.1 onboarding failed on `datamimic_ce, tests_ce` despite its declared
project name (issue #3). Use this standard field rather than reimplementing
setuptools, Hatch and Poetry discovery, or guessing from `tests*` names.
Do not share the adapter's TOML reader: `check` cannot import an adapter and reads
different fields.

Limits: distribution/import-name mismatches (`scikit-learn`/`sklearn`), Poetry 1-only
names and a non-Python `src/` beside a root Python package need explicit scope.
Checks: `tests/test_onboarding.py` covers a matching package, no match, wheel-name
normalization, unreadable/missing names and unchanged ambiguity handling.
