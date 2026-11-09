# AD-323 The native collector reads the syntax facts of a file in one walk

**Decision.** PR 4.3a-1 of issue #880 ports the per-file syntax facts of `analyzer/typescript/parse.py`
to `archkeel-typescript-collector`. The wire reply does not change. It stays the legacy reply of
AD-320, and the 4.2 gap "Script-global dependencies are not examined" stays.

1. **One walk.** `scan.rs` keeps its single walk and gives each node to `walk.rs`. `walk.rs` keeps a
   stack of the ancestors. Each entry holds the nearest scope frame, `var` frame and definition,
   the run of decorators and comments before the next child, and five flags.
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
   siblings come from the stack (`Place`). A definition holds the index of its parent scope.
   `Syntax::parent_name` builds the qualified name on demand. The excerpt of a span is cut from
   the first 1 600 bytes of the node. A line longer than 256 bytes has one column table.
6. **Deep nesting.** The walk and `assignment_targets` use no recursion. Python stops with
   `RecursionError` near a depth of 1 000. Native gives the facts. This is the one closed
   exception to "never complete where Python is UNKNOWN" (decision of 2026-11-08 on #880).
7. **The `dump` feature.** `cargo build --features dump` adds `--dump`. It reads `{"rel", "file"}`
   lines on stdin and prints the facts of each file as JSON. It is not a default feature, so the
   wheel build does not set it. `make native-check` lints it, and the wheel test checks its absence.

**Oracle.** `tests/test_collector_native_syntax.py` compares the dump with `parse.parse()` field by
field. Inputs: the four fixtures, the Studio UI, the resolution grid, the symlink tree, 240 seeded
sources, 88 syntax pieces, 600 mutated files (3 000 with `ARCHKEEL_SYNTAX_MUTANTS`), the hostile
files, the column cases and a private React UI (`ARCHKEEL_PRIVATE_UI`, totals only). The only
differences are the three below. Python is quadratic on huge long-line and nest shapes (614 s for
40 000 functions on one line), so those shapes are compared small and the collector is timed.

**Scaling matrix.** `tests/test_collector_native_scaling.py` builds 93 shapes. It times n and 2n,
and the ratio must stay below 3 (linear is about 2, quadratic about 4). Three shapes also have a
memory bound. A table maps each kind and fact to its shapes, and the dump proves the kinds.

**Differences, a closed list.**
- *Statement order.* `_import_bindings` reads the statements from `QueryCursor.captures`, which
  returns a set of nodes. Its order depends on addresses. The native list is in document order.
  The test compares the bindings of each statement in order.
- *Locale.* The scanner calls C `iswspace`. In a UTF-8 locale, a non-ASCII space before a newline
  ends a statement without a semicolon. In the `C` locale it does not. The native binary acts
  like `C`. AD-325 (merged) sets `LC_ALL=C` for every collector process, so the two now agree.
  The oracle test keeps Python in `C`.
- *Depth.* Point 6.

**Rejected.** Queries for each fact (one tree walk each). Tree nodes in the facts, which would
outlive the tree. A copy of the Python order of the set. A qualified name stored for each definition.
Facts as byte ranges, cut only when needed: revisit in 4.3a-3, when facts go on the wire.

**Limit.** The facts are not on the wire. Sites, comparisons and script facts are later PRs.
- *Quadratic loops, fixed.* The sibling scan read the whole run of comments or decorators for each
  child. `bound_scope` climbed the whole frame chain for each write, and its memo kept an entry
  for each frame and name. It now runs only for a name that the root and another frame both bind.
  Array constants kept their spans in a `Vec`. The triple-slash check of PR 4.2 read root children
  by index: 64 000 lines took 16 s, on the 4.2 binary too.
- *Known limit, not fixed.* A name that the root and the outermost function both bind, written at
  depth n, still costs n squared. 8 000 such imports written in 8 000 nested functions take 4.0 s
  and 3.7 GB, against 0.48 s and 277 MiB on 4.2. A fix needs a stack of frames for each name.
- *No guard on macOS.* The 4 GiB limit of AD-319 exists on Linux and Windows only. macOS has none
  (AD-319 item 4). Memory must grow linearly with the code, not stop at the limit.
- *Dense files, accepted.* Decision of the lead, 2026-11-09, on the advice of the review. Each
  definition costs 1 to 2.8 µs more than in 4.2. The review measured 2.16 times the time for
  50 000 constructor parameters and 2.11 times for 100 000 tiny classes. Peak memory is up to 2.9
  times (57 MiB against 163 MiB). The worst file under the 4 MiB limit takes 615 MiB against 244.
  One class with 838 000 methods takes 1.18 GB against 576 MB. Real code costs 1.10 times on x35.
