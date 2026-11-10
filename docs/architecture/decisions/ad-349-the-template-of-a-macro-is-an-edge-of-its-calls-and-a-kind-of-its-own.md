# AD-349 The template of a macro is an edge of its calls and a kind of its own

**Status.** Accepted. Fable 5.2 chose the combination below for issue #954, item 1. It refines
AD-335 amendment (a).

**Decision.**
1. A `$crate::` path in the body of a `macro_rules!` is an `import` edge of each module that calls
   the macro. A call inside another macro body counts: each macro that the closure reaches gives
   its paths to the module of the first call. The call is also an edge to the module of the macro.
2. The definition keeps its own edge, with the new kind `macro_body` (`archkeel-facts`, protocol 9,
   additive). The host reads the kind in one place, `split_imports` in
   `check/evaluation/imports.py`. It keeps the records out of `scan.imports`, so no rule and no
   other reader sees them. Only the fan-in and fan-out of a module count them.
3. A call is UNKNOWN in the calling module when the scan cannot place it: the call is inside the
   tokens of another macro, or it names the macro by the path of a module.
4. A call is also UNKNOWN when the scan cannot read the body: a relative path, a path from the
   crate name (`::app::b`), a path that `$var` builds, a body nested too deep, or a path that does not resolve. The reason stays UNKNOWN
   in the module of the definition.
5. A path in a string of an attribute in a body (`serde(default = "crate::x::y")`) is read as
   an edge of each call, like any other path of the body.

**Problem.** The template `macros.rs` compiles to nothing. Its paths were edges of `macros`, and
each caller had an edge to `macros`: the report of `native/` showed a false cycle of 12 modules.
**Rejected.** (a) Drop the edge of the definition: the coupling view loses a real source link.
(b) Attribute the path to the definition only: it hides the edge of the caller. (c) Expand the
macro: the scan does not run `rustc`.

**Published.** AD-345 says a published schema never changes. "Published" means contained in a
release tag. Schema 9 is in no release tag yet, so this edit is allowed. It is no precedent once
schema 9 is released.

**Limit.** The scan places a macro by name inside one crate. A macro of another crate, or one that
two modules define, is UNKNOWN as before. The kind widens the committed schema of protocol 9 by one
value; a host that does not know the kind rejects the reply.

**Tests.** `tests/test_collector_false_pass_full.py` (the forbidden edge through a macro, a cycle
through an expansion, no cycle from a template, an unplaced call), `module_edges_tests.rs` and
`schema_tests.rs`, `tests/test_collector_native_macro_bodies.py`.
