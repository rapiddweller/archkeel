# AD-1500 Test source outside the scan roots is no product runtime

**Status.** Accepted. Issue #2240 (cause 1 of 5). It extends the test exclusion of [AD-770](ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md).

**Reason.** The walk of the files outside the scan roots skipped only the directories `test`, `tests` and `__tests__` and the names `test_*.py` and `*_test.py`. The CE repository keeps its tests in `tests_ce/` and a `conftest.py` there does `monkeypatch.setattr(CeBoundedExecutor, "execute", ...)`. That write counted as a write to a class of the scan, so every proof that a call of a class makes an instance (AD-566) was off for the whole scan. Test code is not product runtime, and the stated premise of the run already covers it.

**Decision.** A Python file outside the scan roots is test source, and the walk does not read it, when one of these holds (`survey/outside_testpaths.rs`):
1. `is_test_source` says so (unchanged).
2. Its name is `conftest.py`.
3. It lies under a literal path of `testpaths` in the pytest configuration of the root. The configuration file is chosen as pytest chooses it: `pytest.ini`, then `pyproject.toml` with `[tool.pytest.ini_options]`, then `tox.ini` with `[pytest]`, then `setup.cfg` with `[tool:pytest]`. A glob entry, an absolute entry and an entry with `..` name no path, so no file is left out on a guess.

A `conftest.py` or a test path **inside a scan root** is not touched: the scan reads it as product code, and an import of it by the product is an import of product code.

**Counter-examples that run** (`tests/test_cli_python_outside_test_source.py`, each one with `setattr` on a class of the scan):
- A script outside the roots, a file under a directory that is not in `testpaths`, a glob entry, a `..` entry and a path that only shares a prefix with a test path (`checksum/` against `checks`) all keep the proof withheld (UNKNOWN).
- A `conftest.py` inside the product package that the product imports keeps it withheld.
- A `conftest.py` at any depth outside the roots, and a file under a literal test path, keep the proof (PASS). Mutation: without rules 2 and 3 three tests fail.

**Rejected.** A move of the CE tests to `tests/`: the repository layout is not the tool's to dictate.

**Limit.** The plant `b-outside-roots-conftest` (a `conftest.py` that rebinds a name of the scan) is now a named open false PASS in `tests/python_review_plants.py`, as a write from a file below `tests/` is: pytest runs the write, the product does not. A test file that the product loads at run time by a computed name is the stated premise (AD-770). Test source is not read, so a gap that its own code would give is not given.
