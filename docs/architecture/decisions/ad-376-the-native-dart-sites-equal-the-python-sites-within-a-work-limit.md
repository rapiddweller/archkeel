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
4. Sweeps over the scope ranges and the callable bodies, one cache of the named children of each
   parent and a memo of `_callable_context_for` replace the pairwise loops of Python. They give
   the same values. Python does this work again for each node, so long lists grow with the square.
5. `str.isalnum` of `_canonical_range` reads the `ALNUM` table of the oracle (L-27). It differs
   from `\w` at `_` and at combining marks, and from `char::is_alphanumeric` at U+0345.

**Problem.** The Dart resolver reads the sites: references, calls, creations, bindings and
their scopes. Slice 5 switches the Dart default only when each file equals Python.

**Differences to Python, a closed list (native is equal or stricter).**
- *Depth:* a source with the depth concern of AD-369 (a node at depth 900 or deeper) has no
  sites. Python stops with `RecursionError`, so its sites are not known. Measured in a fresh
  Python 3.11 interpreter: Python stops at tree depth 986 to 989, always first in the `_walk` of
  `_parse_tree`. The recursive site walks `_walk` and `_source_tokens` hold no more frames.
  Nest levels where Python stops: parentheses 982, block closures 246, arrow closures 492, local
  functions 246. This corrects the 170 and 250 of AD-369: those levels count other nest forms
  with the same tree depth. `_ancestors` is a loop, not a recursion. `MAX_DEPTH` stays 900.
- *Work:* the site walks count visited nodes, scanned siblings and copied text. Above
  `64 * size + 2^24` units, the file gets the syntax concern "The site analysis of this Dart
  source stops: ..." and no sites, so the file has a gap. Python has no limit and takes hours on
  such a source. The highest share on the benches is 12.1 % (`flutter`, 6 623 files).
- *Impossible state:* a walk order with a falling start byte, or a body that is not a scope,
  gives the same concern. A Tree-sitter tree cannot have them.

**Rejected.** (a) Port only 3b-1 with a probe (decision 2). (b) The pairwise loops of Python: a
generated 1.8 MB file took 88 s and passed the limit. (c) `Node::parent` for `_ancestors`: it
costs the depth for each step. (d) A recursive token walk, as `_source_tokens`: it overflows.

**Limit.** The parity tools import Python internals; slice 5 replaces that. The Windows gap of
AD-369 stays open.

**Measured (2026-11-12, oracle Python 3.11.12, release build).** Files byte-equal, sites
included: fixtures 151 of 151, demo variants 295 of 295, the private app 28 of 28. Bench samples
with 400 s of Python time each: `dart-http` 287 of 344, `flutter` 917 of 6 623 and 1 file named
by L-27. Native site work on all bench files: at most 12.1 % of the limit, 0 files stopped.

**Tests.** `tests/test_collector_native_dart_sites.py` (50 hostile sources, the depth of each
walk, the work limit), `tests/test_collector_native_dart_syntax.py`,
`native/dart/src/sites_tests.rs`, the tests in `sites/contain.rs`, `sites/canonical.rs`,
`sites/calls.rs` and `pytext_tests.rs`, `tools/dart_unicode_tables.py --check`.
