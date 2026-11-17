# AD-770 Code of the repository outside the scan that writes a module of the scan withholds its routes

**Status.** Accepted (lead decision 1 on #1522). Part of #880, closes #1522. It amends AD-504 and the premise of AD-530 and AD-540.

**Reason.** A script outside the scan roots can replace a re-export: `import app.lib; app.lib.f = secret` makes `from app.lib import f` in `app.consumer` give the private `app.lib._priv.secret`. A C extension can do the same with `PyImport_ImportModule("app.lib")` and `PyObject_SetAttrString`. The premise of the run said only that such code "hands in no module object of the scan". It did not forbid the write, and `interface_boundary` gave PASS.

**Decision.**
1. The survey reads the code of the repository outside the scan modules (`survey/outside.rs`). The walk does not enter `.git`, a symbolic link, `__pycache__`, `node_modules`, a test directory, a directory with `CACHEDIR.TAG` (build output, AD-432) or one with `pyvenv.cfg` (installed packages). It does not read a test file (`is_test_source`, the rule of the test exclusion).
2. A Python file is read with the escape rule of AD-504. A use of a module of the scan that is not a load or call of an attribute escapes that module. A literal import call that names a module of the scan escapes it.
3. A hazard site of such a file (AD-450) can give a module object by its name, so each module of the scan that a string of the file names escapes. Two forms give no module of the scan: an import call whose name is, or starts with, a text that cannot name one (`f"tools.{x}"`, `"a" if c else "b"`), and `exec`, `eval` or `compile` of a literal text without a name.
4. A Python file that Python cannot run (it does not decode or parse at 3.14) writes nothing. A file over the size limit, or with a declared encoding that is not UTF-8, is read as the text of an extension.
5. An extension source (C, C++, Objective-C, Cython, a Rust file that names the C API of Python) and a compiled module are searched for dotted words, also over the size limit (`Snapshot::read_parts`). Two adjacent C string literals are one word. The module that is the longest prefix of a word, each module below it and each package above it escape: native code can walk attributes from the module that it names.
6. An escaped module withholds its routes and its names (AD-504, AD-550). The rules that read them are UNKNOWN with the gap "unproven publication route".
7. The stated premise of the run is now: "Code outside the scan roots, including test code, hands in no module object of the scan and writes no binding of a module or class of the scan." The text header, the JSON `premise` and the report card print it. The #1549 premise seam has not landed; when it lands, this premise becomes a default premise there.

**Why it is sound.** A write that the repository shows contradicts the premise, so the survey withholds the routes that it can change. A test file, a name that code builds at run time from data, and code outside the repository (an installed package, `sitecustomize`, a `.pth` file) are not visible to a reader of the repository. The run states them as its premise with each verdict, so a PASS is never claimed without it.

**Measured.** The FastAPI reference project has no file outside its scan root: PASS 3/0/0. The shell self-check reads 188 Python files outside `src/archkeel` that are not test files. None of them writes a module of `archkeel`, and its three import calls with computed names start with `fixtures.` or are literals of `tools`: 26/0/0. The native self-check is unchanged.

**Tests.** `tests/test_collector_false_pass_python_writers.py` (the two plants of #1522 and a test-file writer under the premise; Python 3.12 confirms the outside write). `survey/outside_tests.rs`, `survey/outside_native_tests.rs`, `snapshot/src/stream_tests.rs`.
