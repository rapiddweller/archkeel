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

**Rejected.** (a) A JSON table for each version: it cannot hold the set of each build. (b) The
tables of the host process: the host `sys.path` and site differ from the isolated child. (c) 10.0.0
in `ProtocolVersion`: the Python codec would then accept it with the semantics of 9.0.0, and the
frozen `ir/` would need a refusal. (d) A second request enum: the Python settings are one variant
of `Resolver` in `archkeel_facts::request`.

**Limit.** `ir/profiles.py` still reads `sys.stdlib_module_names` of the host process; it moves to
the block when the host starts the native Python collector (slice 9). The block has no search
roots yet: the provider phase of slice 2 adds them with its own decision.

**Tests.** `tests/test_collector_native_python_interpreter.py` (the block equals what the isolated
child sees; the Python collector refuses 10.0.0), `tests/test_native_versions.py`,
`native/wire/src/request_tests.rs`, `native/facts/src/schema_tests.rs`.
