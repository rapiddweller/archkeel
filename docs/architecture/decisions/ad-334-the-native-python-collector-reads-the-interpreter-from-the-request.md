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

4. **The parse (slice 1b).** `native/python/src/parse.rs` parses with `ruff_python_parser`
   `=0.0.21` and the target version of the block. A construct of a newer version is a
   `SyntaxError`. `limits.rs` copies the tokenizer rules that ruff does not have, with the text of
   CPython: 200 nested brackets, 100 indentation levels, the tab rule, the unindent rule, a closing
   bracket that does not match, and a bracket that is never closed. The first error by offset wins.
5. **Depth.** `depth.rs` maps the ruff tree to the CPython tree (contexts, operators, `elif`) and
   counts `_ast_depth` without recursion: over 5 000 levels is `TooDeepError` with the depth of
   CPython. Before the parse, the token scan counts the links that make ruff recurse; over
   5 201 is `TooDeepError` "exceeds the parser stack", and CPython fails there too.
6. **Differences, a closed list.** (a) The message of a parser error is the text of ruff. On
   3 000 mutated files the outcome is equal on each file, the class on 2 387 of 2 395 failures and
   the line on 2 328 (3.11; 2 329 on 3.14). (b) Where CPython runs out of its own parser stack (it
   depends on the version), native still gives `TooDeepError` with the depth: AD-323 point 6
   extends to Python by name. The corpus is the 17 files of the PR 5 design (`patho/`: `not`, `+`,
   `lambda`, calls, attributes, lists, brackets, indentation); class and line are equal on 3.11 to
   3.14, and only the message differs.
7. **The 8 class differences** (3.11 and 3.14 alike), each in the `SyntaxError` family: 5 files
   put an indented line after a decorator (CPython `IndentationError` "unexpected indent", ruff
   `SyntaxError` "Expected class, function definition ... after decorator"); 2 files indent line 1
   and have a bracket error on it (native reports the tokenizer error of the bracket); 1 file
   opens a triple-quoted string that never ends (CPython reports the string, ruff a missing
   indented block 10 lines before it).
8. **Comparison of a failure record (lead, 2026-11-11).** The survey parity compares a syntax
   failure record on its file and its exception class (the 8 files of point 7 differ inside the
   `SyntaxError` family); message, line and record id are the
   closed difference of points 6 and 7. The file gets a gap in both producers, never a PASS.

**Rejected.** (a) A JSON table for each version: it cannot hold the set of each build. (b) The
tables of the host process: the host `sys.path` and site differ from the isolated child. (c) 10.0.0
in `ProtocolVersion`: the Python codec would then accept it with the semantics of 9.0.0, and the
frozen `ir/` would need a refusal. (d) A second request enum: the Python settings are one variant
of `Resolver` in `archkeel_facts::request`.

**Limit.** A refused deep tree stays in memory until the process ends: its drop recurses. The
4 MiB file cap bounds it. `ir/profiles.py` still reads `sys.stdlib_module_names` of the host process; it moves to
the block when the host starts the native Python collector (slice 9). The block has no search
roots yet: the provider phase of slice 2 adds them with its own decision.

**Tests.** `tests/test_collector_native_python_interpreter.py` (the block equals what the isolated
child sees; the Python collector refuses 10.0.0), `tests/test_native_versions.py`,
`native/wire/src/request_tests.rs`, `native/facts/src/schema_tests.rs`,
`tests/test_collector_native_python_parse.py` (`ARCHKEEL_PYTHON_PARSE_CORPUS` names a corpus),
`limits_tests.rs`, `depth_tests.rs`, `parse_tests.rs`.
