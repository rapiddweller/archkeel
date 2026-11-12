# AD-376 The native Dart sites equal the Python sites within a work limit

**Status.** Accepted. Epic #880, PR 8 slice 3b. It follows AD-369.

**Decision.**
1. `dart-parse` gives `Syntax.sites` as `_sites` of `analyzer/dart/parse.py` gives it, byte
   for byte. `sites` follows `directives`, in the order of the Python dataclass.
2. This PR ports the whole site range (`parse.py` 1476 to 2423), not only 3b-1. The parity tool
   then compares the real field. A part-port needs a test-only Python probe that calls private
   functions with tree nodes, and a native dump of internal tuples. That is more test code than
   the remaining 470 lines, and it proves parts, not the field.
3. The walk keeps the ancestors of each node, so no rule asks Tree-sitter for a parent: in
   Tree-sitter, `parent()` walks down from the root. Each ancestor holds the facts that
   Python finds with `_ancestors` for each node.
4. Sweeps over the scope ranges and the callable bodies, a memo of `_callable_context_for` and one
   cache of the named children of each parent replace the pairwise loops of Python. The cache
   also holds, for each position, whether a later sibling is a member access, a call or an index.
   The fallback of `_callable_context` reads only the first signature child: the children come
   in the order of their start, which the walk checks. A column continues from the last column
   of its line. Each gives the Python value; Python scans the rest of the list for each node.
5. `str.isalnum` of `_canonical_range` reads the `ALNUM` table of the oracle (L-27). In Python
   3.11 `isalnum` equals `\w` without `_`: over all code points the two differ only at `_`. It
   differs from `char::is_alphanumeric`, for example at U+0345.

**Problem.** The Dart resolver reads the sites: references, calls, creations, bindings and
their scopes. Slice 5 switches the Dart default only when each file equals Python.

**Differences to Python, a closed list (native is equal or stricter).**
- *Depth:* a source with the depth concern of AD-369 (a node at depth 900 or deeper) has no
  sites. Python stops with `RecursionError`, so its sites are not known. Measured in a fresh
  Python 3.11 interpreter: Python stops at tree depth 986 to 989, always first in the `_walk` of
  `_parse_tree`. The recursive site walks `_walk` and `_source_tokens` hold no more frames.
  First nest levels where Python stops: parentheses 981 (depth 986), block closures 246, arrow
  closures 491 (depth 987), local functions 246. This corrects the 170 and 250 of AD-369: those levels count other nest forms
  with the same tree depth. `_ancestors` is a loop, not a recursion. `MAX_DEPTH` stays 900.
- *Work:* the site walks count each visited node, scanned sibling, read candidate, copied text
  and byte decoded for a column. No loop of the walks is uncounted, so the work is bounded.
  Above `64 * size + 2^24` units, the file gets the syntax concern "The site analysis of this
  Dart source stops: ..." and no sites, so the file has a gap. Python has no limit and takes
  hours on such a source. A cascade of 40 000 sections on one line stops: the Python texts of
  its member references grow with the square. The highest share on the benches is 14.4 %.
- *Impossible state:* a walk order with a falling start byte, or a body that is not a scope,
  gives the same concern. A Tree-sitter tree cannot have them.

**Rejected.** (a) Port only 3b-1 with a probe (decision 2). (b) The pairwise loops of Python: a
generated 1.8 MB file took 88 s and passed the limit. (c) `Node::parent` for `_ancestors`: it
costs the depth for each step. (d) A recursive token walk, as `_source_tokens`: it overflows.

**Limit.** The parity tools import Python internals; slice 5 replaces that. The Windows gap of
AD-369 stays open.

**Amendment (#1079): the definitions use the same limit.** The definition walks read the named
children of each parent once from the cache, and count each child, scanned sibling, column byte
and copied head of a declaration item. Past the limit the file gets "The definition analysis of
this Dart source stops: ..." and no definitions or sites. One list item copies the declaration
head, as in Python, so a declaration of 20 000 items stops. 20 000 members or top-level
definitions took 27 to 108 s and now take under 1 s. The memory of 5 MB of `(` (4.3 GB) is
Tree-sitter's stack, not a rule. A source with over 9 000 open brackets (`(`, `[`, `{`, strings
too, the stricter choice) is not parsed and gets the depth concern. Rejected: a cap on bytes.

**Measured (2026-11-12, oracle Python 3.11.12, release build).** Files byte-equal, sites
included: fixtures 151 of 151, demo variants 295 of 295, the private app 28 of 28. Bench samples
with 400 s of Python time each: `dart-http` 287 of 344, `flutter` 917 of 6 623 and 1 file named
by L-27. Native site work on all bench files: at most 14.4 % of the limit, 0 files stopped.

**Tests.** `tests/test_collector_native_dart_sites.py` (60 hostile sources, the depth of each
walk, the work limit, five shapes that Python scans again for each node), `tests/test_collector_native_dart_syntax.py`,
`native/dart/src/sites_tests.rs`, `tests/test_collector_native_dart_definitions.py`,
`native/dart/src/definitions_tests.rs`, `native/dart/src/nesting.rs`, the tests in `sites/contain.rs`, `sites/canonical.rs`,
`sites/calls.rs` and `pytext_tests.rs`, `tools/dart_unicode_tables.py --check`.
