# AD-323 The native collector reads the syntax facts of a file in one walk

**Decision.** PR 4.3a-1 of issue #880 ports the per-file syntax facts of `analyzer/typescript/parse.py`
to `archkeel-typescript-collector`. The wire reply does not change: it stays the legacy reply of
AD-320, and the 4.2 gap "Script-global dependencies are not examined" stays.

1. **One walk.** `scan.rs` keeps its single walk and gives each node to `walk.rs`. `walk.rs` keeps a
   stack of the ancestors. Each entry holds the frame of the nearest scope, the nearest `var`
   frame, the nearest definition, the run of decorators and comments before the next child, and
   five flags. `parse.py` runs about ten walks and climbs the parents.
2. **Facts.** The walk produces these fields of `Syntax`: `definitions`, `import_bindings`,
   `module_exports`, `rebound_names`, `ambient_globals`, `ambient_top_level`, `module_file`,
   `declaration_file`, `script_mode` and `script_bindings`. The structs are owned. No tree node
   outlives its file.
3. **Scope frames.** `scope.rs` keeps the frames in a `Vec`. A frame knows its parent, counts the
   bindings of each name and can be ambiguous. A lookup climbs the chain (`_script_bound_scope`).
4. **Kinds and fields.** `kinds.rs` maps each id of the grammar to one enum built from `_NodeKind`,
   and each field name that the walk reads to its id. A named kind and a token of the same text are
   one kind. A text that `_NodeKind` does not list is `K::Other`.
5. **Cost.** No question climbs the tree. The parent kind, the grandparent kind and the run of
   siblings come from the stack (`Place`). A definition holds the index of its parent scope, and
   `Syntax::parent_name` builds the qualified name on demand, as `parent_name` of Python. The
   excerpt of a span is cut from the first 1 600 bytes of the node. The UTF-16 column of a line
   longer than 256 bytes comes from one table for the line. The first version did not: 33.6 s for
   40 000 functions on one line, 61 s and 1.3 GB for 8 000 nested classes (release build).
6. **Deep nesting.** The walk and `assignment_targets` use no recursion. Python stops with
   `RecursionError` near a depth of 1 000. Native gives the facts. This is the one closed
   exception to "never complete where Python is UNKNOWN" (decision of 2026-11-08 on #880).
7. **The `dump` feature.** `cargo build --features dump` adds `--dump`: it reads
   `{"rel", "file"}` lines on stdin and prints the facts of each file as JSON. `dump` is not a
   default feature. The wheel build does not set it. `make native-check` lints it, and the
   installed wheel binary is tested for its absence.

**Oracle.** `tests/test_collector_native_syntax.py` compares the dump with `parse.parse()` field by
field on the four fixtures, the Studio UI, the resolution grid, the symlink tree, 240 seeded
sources, sources built from 69 syntax pieces, 600 mutated files (3 000 with
`ARCHKEEL_SYNTAX_MUTANTS`), the hostile files, moderate sizes of the long-line and nest shapes
and a private React UI (`ARCHKEEL_PRIVATE_UI`, totals only). There are no differences except the
three below. The huge sizes of those shapes have no oracle: Python is quadratic on them too (614 s
for 40 000 functions on one line). Their test bounds the wall time of the collector process. The
cargo tests hold values that `parse.parse()` printed.

**Differences, a closed list.**
- *Statement order.* `_import_bindings` reads the statements from `QueryCursor.captures`, which
  returns a set of nodes. Its order depends on addresses. The native list is in document order,
  and the test compares the bindings of each statement in order.
- *Locale.* The scanner of the grammar calls C `iswspace`. In `en_US.UTF-8` and `C.UTF-8`, any
  non-ASCII space before a newline (U+00A0, U+2003, U+3000, U+2028, U+2029) ends a statement
  that has no semicolon. In the `C` locale it does not. `const a = 1<U+00A0>\nconst b = 2` gives
  1 binding under `LC_ALL=C` and 2 under the other two. The native binary never calls
  `setlocale` and behaves like `C`. Python sets the locale from the environment, and PEP 538
  makes an unset locale `C.UTF-8`, so on a default Linux or Docker host Python and native
  differ. The severity is low: it needs a statement without a semicolon that ends in such a
  space. 778 real files gave the same facts in both locales. The remedy is a separate PR that
  pins `LC_ALL=C` for collector processes in `analyzer/process.py`. Until then the test runs
  the oracle in `C`.
- *Depth.* Point 6.

**Reason.** The next PRs need these facts for sites, symbols and records. One walk gives them once;
Python needs about 26 s for them on 910 files.

**Rejected.** Queries for each fact (one tree walk each). Tree nodes in the facts (they would
outlive the tree). A copy of the Python order of the set. A qualified name stored for each definition.

**Limit.** The facts are not on the wire. Sites, comparisons and script facts are later PRs. The
qualified name at depth n has n names, as in Python: a consumer that builds it for each definition
pays the depth each time.

**Check.** `tests/test_collector_native_syntax.py`, `tests/test_collector_native_wheel.py`, the
`walk`, `scope` and `kinds` tests in `native/`, and `make native-check`.
