# AD-528 A `sys.path.append` that adds no imported name is no gap

**Status.** Proposed. Part of #880. It narrows the `import_system_change` gap of AD-450 for one
write form. It follows AD-504 (Open false PASS) and the proof review of its design.

**Reason.** K-python-realworld writes `sys.path.append(str(pathlib.Path(__file__).resolve().parents[3]))`
in `app/db/migrations/env.py` (an Alembic file). The gap held the whole run: the core gave 0/0/1
and 4.0.1 gives 6/0/1. The write appends the repository root, which holds the scan root `app`;
among its module-like entries (`app`, `contracts`, `docs`) only `app` is imported.

**What a write can change.** Only the module that a first segment of an absolute import finds.
`append` adds a directory behind the standard library and the project; `insert` can put it before.

**Decision.** One form is no gap; every other write of `sys.path` stays the gap of the whole run.
The form is harmless when the directory `P` adds no module-like entry that the scan imports:
- R1 `append` only; `insert` at any index keeps the gap.
- R2 the conflict set holds the first segment of each import target, of the namespace and of each
  literal import call, folded to lower case.
- R3 the entry of the namespace is exempt only when `P/n` is itself a scan root, the namespace is
  `n`, `P/n/__init__.py` exists and no other entry of `P` is named `n`.
- R4 a module-like entry is any directory or link, or a file `n.py`, `n.pyc`, `n.pyw`, `n.so`,
  `n.pyd`, `n.<tag>.so`, `n.<tag>.pyd`, compared without case. A listing with a problem or a hidden
  entry refuses (`Snapshot::entries`, `hidden_entries`).
- R5 the expression is `Path(__file__).resolve()` or `pathlib.Path(__file__).resolve()` followed by
  `.parent` or `.parents[k]` (k a non-negative integer literal), inside `str()`; the statement is an
  expression statement of the module body; `sys`, `pathlib` or `Path` have one plain import binder
  each; `str` and `__file__` have none (a star import refuses); no part of the file path is a
  link; `P` is inside the snapshot.
Two writes where one is refused keep the gap. The listing of `P` is a digest input of the reply
(path ending with `/`, sorted names); the core reads it again, so the verdict is bound to the
names it depends on.

**Where the core and 4.0.1 differ.** 4.0.1 reads no `sys.path` write, so it gives PASS for every
plant of `tests/python_syspath_plants.py`; the core gives the same rows for the control and
UNKNOWN for the others (stricter, never weaker). K-python-realworld: 6/0/1, as 4.0.1.

**Limits (named in `docs/known-limits.md`).** The verdict holds for a run from the snapshot tree:
a copied, installed or zipped layout, a direct run of a `.pyc`, `run_path` with a relative path and
`os.chdir` give another `P`. Entries that appear in `P` after the snapshot are not seen. A writer
outside the scan roots (`conftest.py`, `sitecustomize`, an installed package) is an open false
PASS, as before. A name of `P` that only code outside the scan imports is not seen. The rule
assumes that the namespace resolves to the scan root.

**Tests.** `tests/test_cli_python_syspath.py` runs the control and 38 plants through the release
core (`tests/python_syspath_plants.py`); `native/python/src/survey/syspath_tests.rs` runs the forms
on the survey. The mutation table is in the PR.
