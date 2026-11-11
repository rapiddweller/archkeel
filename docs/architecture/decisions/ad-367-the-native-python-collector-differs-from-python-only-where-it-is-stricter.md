# AD-367 The native Python collector differs from Python only where it is stricter

**Status.** Accepted. PR 5 of issue #880; it holds the closed list of differences of AD-334.

**Rule (owner).** A documented limit must never hide a silent false PASS. What the collector does
not see soundly gives a named gap (UNKNOWN). A difference is allowed only when the native verdict
is equal or stricter. Each item below names its test.

**Parse** (`tests/test_collector_native_python_parse.py`).
1. The message of a parser error is the text of ruff. On 3 000 mutated files accept or refuse is
   equal on each file, the class on 2 387 of 2 395 failures and the line on 2 328 (3.11; 2 329 on
   3.14). The survey compares a syntax failure record on its file and its exception class family;
   message, line and record id differ. The file gets a gap in both producers, never a PASS.
2. The 8 class differences stay in the `SyntaxError` family: 5 files put an indented line after a
   decorator (CPython `IndentationError` "unexpected indent", ruff "Expected class, function
   definition ... after decorator"); 2 files indent line 1 and have a bracket error on it (native
   reports the bracket); 1 file opens a triple-quoted string that never ends (CPython reports the
   string, ruff a missing indented block 10 lines before it). Each file gets a gap in both.
3. Stricter parse outcomes (`STRICTER` in `tests/test_collector_native_python_hostile.py`, 320
   hostile sources on 3.11 to 3.14). (a) CPython stops past `MAXSTACK` = 6 000 rule calls; the
   cost of a nesting depends on its grammar context, so native sums a measured upper bound (AD-334
   point 5) and refuses with `TooDeepError` some files that CPython accepts, for example 124 to
   200 brackets, 2 961 to 5 967 `not` or nested conditional expressions, 124 to 149 nested
   f-strings: a gap (AD-323 point 6 by name). Real code stays under 600 of 6 000. (b) `<>` after
   `barry_as_FLUFL` (3.12+): ruff refuses it. (c) Over 4 300 digits in an f-string on 3.11: 11.

**Scope** (`tests/test_collector_native_python_scope.py`, `discover_tests.rs`).
4. A file over 4 MiB (AD-319) is selected and is an `Unseen::Oversized` value; the survey writes a
   collection gap that names it, so its scope is never PASS. The file is no input, and its bytes
   are not in the source digest: a change of the file does not change the digest, and the gap
   makes that irrelevant, because the scope stays UNKNOWN while the file is over the limit.
5. A dangling `*.py` link inside the snapshot, not under `__pycache__`: Python selects it and its
   read fails with `FileNotFoundError`; native selects it (`Unseen::Missing`) and writes the same
   failure. Equal. Stricter: a dangling link that resolves outside the snapshot or into a test
   path under the test exclusion, which Python leaves out, gets the failure and a gap. A symlink
   loop is `Missing`: point 12. Under the test exclusion each dangling link is a gap that names it
   and `full_scope` is false: Python also judges its target, native cannot (L-30). Stricter.
6. A name that is not UTF-8 (Linux; macOS refuses it), or a FIFO, a socket or a device named
   `*.py`: Python selects the file (the read of a FIFO blocks until the timeout). Native never
   reads it and writes a collection gap that names it (`Unseen::NotUtf8`, `Unseen::Special`).
7. An unreadable directory: Python skips it silently, and native keeps parity. Both producers
   change together under #1043 (P2).
8. `pyproject.toml` that `tomllib` reads and native refuses, so the state is `metadata_invalid`
   instead of `declared`: an integer beyond 64 bits, a bare CR (`read_text` makes it a newline),
   a file over 4 MiB (AD-319). `metadata_invalid` gives a runtime diagnostic and no declared
   range (`check/runtime.py`), so it is never more PASS. A dangling link is `metadata_invalid`
   where Python writes `metadata_missing`: both give the same diagnostic kind and no range. A
   Poetry caret over 64 bits stays unexpanded; `check/runtime.py` refuses it as unsupported where
   Python declares a range that no Python satisfies: a diagnostic in both.

**Records.** 9. `ShadowedModule` (#797) is an exception name of protocol 10.0.0 only; the 9.0.0
schema stays byte-equal. The survey writes the gap in slice 1c-2, and no native Python reply can
be PASS before it does (AD-334: the host does not decode 10.0.0).

**Read** (`tests/test_collector_native_python_survey.py`).
10. A selected file that exists but does not open (for example mode 000): Python writes the class
    of the errno (`PermissionError`), native writes `OSError`, because `Snapshot::read` does not
    keep the error kind. Both producers write a gap that names the file, so the verdict is equal.
    The comparison rule for this case only: the file and its gap are present in both producers,
    and the exception class may be the base class `OSError`; the rest of the survey is equal.

**Stops of the Python collector** (L-20, `tests/test_collector_native_python_reply.py`).
11. Over 4 300 digits in an f-string: CPython 3.11 raises `SystemError` (3.12 on: a failure).
12. A symlink loop (`cyc.py`, `cyc2.py`): 3.11 and 3.12 raise `RuntimeError` (3.13 on: point 10).
The Python collector does not catch the error, and its run stops without a verdict. Native writes
a failure record and a gap for each file, so the run is never PASS-complete. Accepted (L-20).

**Rejected.** (a) Gaps only in the documentation: a limit without a gap can hide a false PASS.
(b) Reading a file over 4 MiB for the digest only: the size limit is the defence of AD-319.
(c) A difference where native is less strict: it is a bug of the native collector.
