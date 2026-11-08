# AD-323 The native collector reads the syntax facts of a file in one walk

**Decision.** PR 4.3a-1 of issue #880 ports the per-file syntax facts of `analyzer/typescript/parse.py`
to `archkeel-typescript-collector`. The wire reply does not change: it stays the legacy reply of
AD-320, and the 4.2 gap "Script-global dependencies are not examined" stays. The facts are the
input of the record producers in the next PRs.

1. **One walk.** `scan.rs` keeps its single walk and gives each node to `walk.rs`. `walk.rs` keeps a
   stack of the ancestors. Each entry holds the frame of the nearest scope, the nearest `var`
   frame, the nearest definition and five flags (a repaired node above, a namespace above, a
   statement block that is not a `body`, a rebound-name function above, a function-like node above).
   `parse.py` runs about ten walks and climbs the parents for each question.
2. **Facts.** The walk produces these fields of `Syntax`: `definitions`, `import_bindings`,
   `module_exports`, `rebound_names`, `ambient_globals`, `ambient_top_level`, `module_file`,
   `declaration_file`, `script_mode` and `script_bindings`. The structs are owned. No tree node
   outlives its file.
3. **Scope frames.** `scope.rs` keeps the frames in a `Vec`. A frame knows its parent, counts the
   bindings of each name and can be ambiguous. A lookup climbs the chain (`_script_bound_scope`).
4. **Kinds.** `kinds.rs` maps each id of the grammar to one enum, built from `_NodeKind`. A named
   kind and a token of the same text are one kind, as in `_node_kind`. A text that `_NodeKind` does
   not list is `K::Other`, as `_node_kind` gives `None`.
5. **Deep nesting.** The walk and `assignment_targets` use no recursion. Python stops with
   `RecursionError` near a depth of 1 000. Native gives the facts. This is the one closed
   exception to "never complete where Python is UNKNOWN" (decision of 2026-11-08 on #880).
6. **The `dump` feature.** `cargo build --features dump` adds `--dump`: it reads
   `{"rel", "file"}` lines on stdin and prints the facts of each file as JSON. `dump` is not a
   default feature. The wheel build does not set it.

**Oracle.** `tests/test_collector_native_syntax.py` compares the dump with `parse.parse()` field by
field on the four fixtures, the Studio UI, the resolution grid, the symlink tree, 240 seeded
sources, 368 sources built from 68 syntax pieces, 600 mutated files (3 000 with
`ARCHKEEL_SYNTAX_MUTANTS`), the hostile files and a private React UI (`ARCHKEEL_PRIVATE_UI`,
totals only). There are no differences except the three below. The cargo tests hold values that
`parse.parse()` printed.

**Differences, a closed list.**
- *Statement order.* `_import_bindings` reads the statements from `QueryCursor.captures`, which
  returns a set of nodes. Its order depends on addresses. The native list is in document order,
  and the test compares the bindings of each statement in order.
- *Locale.* The scanner of the grammar calls C `iswspace`. In `en_US.UTF-8`, U+2028 ends a
  statement. In the `C` locale it does not. The Python collector takes its locale from the
  environment, so its output changes with it. The native process never sets a locale. The test
  runs the oracle in `C`.
- *Depth.* Point 5.

**Reason.** The next PRs need scope, definitions and bindings for sites, symbols and records. One
walk gives them once. The equal-work floor of Python for these facts is about 26 s on 910 files.

**Rejected.** Queries for each fact (the 4.2 cost: one tree walk each). Keeping tree nodes in
the facts (they would outlive the tree). A copy of the Python order of the set.

**Limit.** The facts are not on the wire. Sites, comparisons and script facts are later PRs.

**Check.** `tests/test_collector_native_syntax.py`; the `walk` and `kinds` tests in `native/`;
`make native-check`.
