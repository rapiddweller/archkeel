# AD-334 The native Python collector reads the interpreter from the request

**Status.** Accepted. PR 5 slice 1 of issue #880 (decisions of 2026-11-09 and 2026-11-10, Q2).

**Decision.**
1. **Protocol 10.0.0.** It is the request of the native Python collector only. It has the scope
   of 9.0.0 and the resolver `{"language": "python", "phase": "imports", "interpreter": {...}}`.
   The Python resolver needs 10.0.0, and 10.0.0 needs the Python resolver. The reply is the 9.0.0
   reply with `protocol_version` 10.0.0. The one list is `Version::ALL` in
   `native/facts/src/protocol.rs`. The host names 10.0.0 once, `NATIVE_PYTHON_PROTOCOL` in
   `analyzer/interpreter.py`, the one builder of the request, so `ir/` stays unchanged.
   `tests/test_native_versions.py` compares both with the schema.
2. **The interpreter block.** It is closed: `version` (the full `platform.python_version()`,
   such as `3.11.12`), `stdlib_module_names` and `builtin_module_names` (sorted). The built-in
   set depends on the build, not on the version (31 modules on Homebrew 3.12, 101 on uv 3.11).
   One host function, `analyzer/interpreter.py:interpreter()`, builds it from one `python -I`
   child, the interpreter of the Python collector child. The collector accepts 3.11 to 3.14.
3. **The Python collector stays unmodified.** The Python codec does not read 10.0.0: the Python
   collector refuses the request, and the host cannot decode a 10.0.0 reply. So no native Python
   reply can be a PASS before slice 8.

4. **The parse (slice 1b).** `parse.rs` parses with `ruff_python_parser` `=0.0.21` and the
   version of the block; a newer construct is a `SyntaxError`. `limits.rs` copies with the CPython
   text what ruff does not check: 200 brackets, 100 indentation levels, the tab and unindent rules,
   bracket matching, a bracket never closed, over 4 300 decimal digits (the child runs with `-I`),
   a second byte order mark, 150 nested f-strings (3.12+), the 3.11 f-string rules (a spec in a
   spec, a lone `*a`, 200 brackets in a field) and `!=` after `barry_as_FLUFL` (3.12+).
   `identifier.txt` lists the name characters that ruff (Unicode 17) accepts and each CPython
   (Unicode 14 to 16) refuses. On 3.14 `parse.rs` checks a leading `from __future__` import as
   `ast.parse` does. The first error by offset wins.
5. **Depth.** `depth.rs` counts `_ast_depth` on the ruff tree without recursion: over 5 000 is
   `TooDeepError` with the depth. CPython stops with `MemoryError` past `MAXSTACK` = 6 000 rule
   calls (3.11 to 3.14). The calls of one nesting depend on its grammar context, so `stack.rs`
   sums a bound for each nesting, measured on 3.11 to 3.14 (maximum in brackets): a statement 80
   (54), a block 10 (8), a bracket 48 (37), a `lambda` 10 (8), an `else` 2 (1), a unary sign,
   `not` or `await` 2 (1), a `**` 3 (2). Over 6 000 is `TooDeepError` before the parse (an error
   of the scan wins). Real code: at most 522 (`src/`), 582 (`tests/`), 390 (pydantic), 378
   (fastapi), 476 (private package).
6. **Differences, a closed list** (`STRICTER` in `tests/test_collector_native_python_hostile.py`).
   (a) A parser error has the text of ruff: on 3 000 mutated files the outcome is equal, the class
   on 2 387 of 2 395 failures, the line on 2 328 (3.11; 2 329 on 3.14). (b) The stack bound is
   stricter: native refuses with `TooDeepError` (a gap, AD-323 point 6 by name) what CPython
   accepts, for example 124 to 200 brackets, 2 961 to 5 967 `not`, 593 to 2 983 `lambda`, 124 to
   149 nested f-strings. A deep tree can get the stack message instead of its depth. (c) `<>`
   after `barry_as_FLUFL` (3.12+): CPython accepts it, ruff refuses it. (d) CPython 3.11 raises
   `SystemError` for over 4 300 digits in an f-string, which the Python collector does not catch,
   so its run stops; native writes a `SyntaxError` record. No tree in both.
7. **The 8 class differences** (3.11 and 3.14), each in the `SyntaxError` family: 5 files indent
   a line after a decorator (CPython "unexpected indent", ruff "Expected class, function
   definition ... after decorator"); 2 indent line 1 with a bracket error on it (native reports
   the bracket); 1 never ends a triple-quoted string (ruff reports a block 10 lines before it).
8. **Comparison of a failure record (lead, 2026-11-11).** The survey parity compares a syntax
   failure record on its file and its exception class; message, line and record id are the closed
   difference of points 6 and 7. The file gets a gap in both producers, never a PASS.
9. **Scope (slice 1c-1).** `discover.rs`, `names.rs`, `inputs.rs` and `requirement.rs` copy
   `selected_paths` (rglob: a directory named `*.py` is selected, a symlinked directory is not
   entered), the test rule, `module_for`, the shadowed module (#797), `_inputs` (digest of
   `path\0bytes\0`) and `python_requirement` (`toml` 0.8.23 reads TOML 1.0, as `tomllib`).
   Proposed differences: a file over 4 MiB is no input (AD-319); an integer beyond 64 bits makes
   `pyproject.toml` invalid; a dangling link, a name that is not UTF-8 and an unreadable directory
   select nothing. The typed `ShadowedModule` gap waits: the 9.0.0 schema lacks the name.

**Rejected.** (a) A JSON table for each version: it cannot hold the set of each build. (b) The
tables of the host process: the host `sys.path` and site differ from the isolated child. (c) 10.0.0
in `ProtocolVersion`: the Python codec would then accept it with the semantics of 9.0.0, and the
frozen `ir/` would need a refusal. (d) A second request enum: the Python settings are one variant
of `Resolver` in `archkeel_facts::request`.

**Limit.** A refused deep tree stays in memory until the process ends (its drop recurses); the
4 MiB file cap bounds it. `ir/profiles.py` reads `sys.stdlib_module_names` of the host until the
host starts the native collector (slice 9). Search roots come with the provider phase (slice 2).

**Tests.** `tests/test_collector_native_python_interpreter.py` (the block equals what the isolated
child sees; the Python collector refuses 10.0.0), `test_native_versions.py`, `request_tests.rs`,
`schema_tests.rs`, `test_collector_native_python_parse.py` (`ARCHKEEL_PYTHON_PARSE_CORPUS` names a
corpus), `test_collector_native_python_hostile.py` (320 hostile sources and the identifier table
against the running CPython), `limits_tests.rs`, `depth_tests.rs`, `parse_tests.rs`.
