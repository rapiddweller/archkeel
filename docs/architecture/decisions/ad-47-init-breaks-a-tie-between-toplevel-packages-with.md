# AD-47 `init` breaks a tie between top-level packages with `pyproject.toml`'s `[project] name`, and with nothing else

`detect_source` still takes the only top-level package under `src/`, or
under the root without `src/`, when there is exactly one. When there are several, it reads
`[project] name` from the root `pyproject.toml`, puts it in wheel file-name form (runs of `-`,
`_` and `.` become `_`, lowercased) and keeps the one package whose lowercased directory name
equals it. A missing or unreadable file, no declared name, or zero or two matching packages
still end in exit 2 with the same `scope_empty` diagnostic and `--source`/`--namespace` remedy;
its claim now also names the project name it compared, or `missing`. Reason: onboarding
`datamimic_ce` with 0.4.1 stopped at `found datamimic_ce, tests_ce` although its
`pyproject.toml` declares `name = "datamimic_ce"` (issue #3). A package beside its test package
is the common layout, and `[project] name` is PEP 621's one standard field, the name hatch,
poetry and flit already assume for the import package when no package list is declared.
Rejected: reading the build backends' own package declarations
(`[tool.setuptools] packages` and `packages.find`, `[tool.hatch.build.targets.wheel] packages`,
`[tool.poetry] packages`) was rejected because it is three dialects with their own glob,
`where` and `from` semantics, and the motivating repository declares only
`[tool.setuptools.packages.find] where = ["."]`, `exclude = ["tests_ce"]`, `namespaces = true`:
reproducing that answer means reimplementing setuptools' `find` discovery, where
`namespaces = true` also counts directories without `__init__.py`, for an answer
`[project] name` gives in one comparison. Excluding packages named `tests*` was rejected
because it guesses from a naming convention instead of reading a declaration: it misses `test/`
and `spec/`, widening it to `test*` would also drop real packages such as `testcontainers`,
and with two real packages beside a test package it would still choose by elimination, the
silent guess the `scope_empty` exit exists to prevent. Sharing `analyzer/runtime.py`'s
`pyproject.toml` read was rejected because `check` may not import an adapter, and the two
reads take different fields. Limit: a distribution named differently from its import package
(`scikit-learn` and `sklearn`), a name declared only under Poetry 1's `[tool.poetry]`, and a
`src/` directory holding no Python package beside a root-level one (a Rust crate, as in
DataMimic EE) still exit 2 and need `--source` and `--namespace`; a single package is taken
without comparing the name, as before. Check: `tests/test_onboarding.py`'s
`test_init_picks_the_package_the_project_is_named_after` (`src/archkeel` beside
`src/tests_pkg`, `name = "archkeel"`), `test_init_stays_ambiguous_when_no_package_matches_the_project_name`
(`src/archkeel_core` beside `src/tests_pkg`, exit 2 naming both packages and the compared name),
`test_detect_source_matches_the_project_name_in_wheel_file_name_form` (the issue's flat layout,
with `archkeel_core`, `Archkeel-Core` and `archkeel.core`),
`test_detect_source_fails_closed_without_a_readable_project_name` (no file, invalid TOML, no
`name`) and the unchanged `test_init_asks_for_the_source_when_the_package_is_ambiguous`.

