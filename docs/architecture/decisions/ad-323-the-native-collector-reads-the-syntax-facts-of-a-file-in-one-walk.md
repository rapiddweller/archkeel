# AD-323 The native collector reads the syntax facts of a file in one walk

**Decision.** PR 4.3a-1 of issue #880 ports the per-file syntax facts of `analyzer/typescript/parse.py` (retired by AD-394)
to `archkeel-typescript-collector`. The wire reply stays the legacy reply of AD-320, and the 4.2
gap "Script-global dependencies are not examined" stays.

1. **One walk.** `scan.rs` keeps its single walk and gives each node to `walk.rs`. `walk.rs` keeps a
   stack of the ancestors. Each entry holds the nearest scope frame, `var` frame and definition,
   the run of decorators and comments before the next child, and five flags.
2. **Facts.** The walk produces these fields of `Syntax`: `definitions`, `import_bindings`,
   `module_exports`, `rebound_names`, `ambient_globals`, `ambient_top_level`, `module_file`,
   `declaration_file`, `script_mode` and `script_bindings`. The structs are owned. No tree node
   outlives its file.
3. **Scope frames.** `scope.rs` keeps the frames in a `Vec`. A frame knows its parent, counts the
   bindings of each name and can be ambiguous. A lookup climbs the chain (`_script_bound_scope`).
4. **Kinds and fields.** `kinds.rs` maps each grammar id to one enum built from `_NodeKind` (a text
   that it does not list is `K::Other`), and each field name that the walk reads to its id.
5. **Cost.** No question climbs the tree. The parent kind, the grandparent kind and the run of
   siblings come from the stack (`Place`). A definition holds the index of its parent scope, and
   `Syntax::parent_name` builds the qualified name on demand. A line over 256 bytes has one column
   table, and an excerpt is cut from the first 1 600 bytes of the node.
6. **Deep nesting.** The walk and `assignment_targets` use no recursion. Python stops with
   `RecursionError` near a depth of 1 000. Native gives the facts. This is the one closed
   exception to "never complete where Python is UNKNOWN" (decision of 2026-11-08 on #880).
7. **The `dump` feature.** `--dump` (feature `dump`, not a default) reads `{"rel", "file"}` lines and
   prints the facts of each file as JSON. `make native-check` lints it; the wheel test checks its absence.

**Oracle.** `tests/test_collector_native_syntax.py` compares the dump with `parse.parse()` field by
field: the fixtures, the Studio UI, the resolution grid, seeded and mutated sources (3 000 with
`ARCHKEEL_SYNTAX_MUTANTS`), hostile files, column cases and a private React UI (`ARCHKEEL_PRIVATE_UI`,
totals only). **Scaling matrix.** `tests/test_collector_native_scaling.py` and
`tests/test_collector_native_scaling_sites.py` time n and 2n; the CPU ratio must stay below 3
(linear is about 2, quadratic about 4). Some shapes have a memory bound. A table maps each kind and
fact to its shapes, and the dump proves the kinds.

**Differences, a closed list.** *Statement order:* `_import_bindings` reads a set of nodes, so its
order depends on addresses; native is in document order, and the test compares each statement in
order. *Locale:* the scanner calls C `iswspace`; AD-325 sets `LC_ALL=C` for every collector, so the
two agree, and the oracle keeps Python in `C`. *Depth:* point 6.

**Rejected.** A tree walk for each fact. Tree nodes in the facts. A stored qualified name. Byte
ranges for definitions: done for sites (below), open for 4.3a-3.

**Limit.** The facts are not on the wire. Records for sites are PR 4.3a-3, script facts 4.3a-4.
- *Fixed.* A scan of the run of comments or decorators for each child; a write lookup that
  climbed all frames, with a memo for each frame and name (now only for a name that the root and
  another frame both bind); array spans in a `Vec`; the triple-slash check of PR 4.2.
- *Known limit, not fixed.* A name that the root and the outermost function both bind, written at
  depth n, costs n squared: 8 000 imports written in 8 000 nested functions take 4.0 s and 3.7 GB
  (4.2: 0.48 s, 277 MiB). A fix needs a stack of frames for each name.
- *No guard on macOS* (AD-319 limits Linux and Windows only): memory must grow linearly.
- *Dense files, accepted* (lead, 2026-11-09): up to 2.2 times the time of 4.2 and 2.9 times the
  memory; 1.10 times on real code (x35). Absolute, under the 4 MiB limit: 100 000 tiny classes
  615 MiB against 244 MiB, one class of 838 000 methods 1.18 GB against 576 MB.

**Amendment, 2026-11-09 (PR 4.3a-2): sites and string comparisons.** The walk also collects `sites`
and `string_comparisons` (`_sites`, `_call_site`, `_target_name`, `_static_path`,
`_active_scope_names`, `_scope_names`, `_comparison_literal`). The reply differs only in the code digest.
1. A stack entry also holds the callee flag (`_inside_site_callee`), a chain of the scopes that hide
   names, and whether an `arguments` node belongs to a wrapper of a script; three flags join the
   five (in a type, in a `window.x` publication, in a `with`). A site reads its parent and grandparent.
2. A site keeps byte ranges, not strings. A static path is an item of an arena that points at its
   receiver, with a memo by node: `a.b.c.d` costs four items, not ten names.
3. Shadowed names are a chain: the walk writes each candidate name once to two lists in document
   order, a scope keeps two byte ranges, a site keeps a link. Only the dump unites a chain; a set for
   each site is n squared for n nested functions.
4. `Frames::free_index` numbers the frames in document order. A name keeps the ranges of the frames
   that bind it, and one binary search answers `_script_free`: no climb, no growing memo.
5. No new difference. A shorthand property is a reference in a script only. 127 shapes (the sites
   run joined in 8 timed shapes) and 12 memory bounds (peak for 2n at most 2.5 times n).
