# AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls

`resolve_name` types `recv.method(...)` from:

- A direct string or f-string literal.
- A local whose own-scope bindings all agree on list, dict, set or string literals,
  or unshadowed `list()`/`dict()`/`set()` calls. A matching annotation is compatible.
- A parameter or local with only an annotation binding for `list`, `dict`, `set`,
  `frozenset`, `tuple`, `str` or `pathlib.Path`/`Path`, including generic subscripts.

A conflicting or non-literal binding invalidates the name for the whole function:
plain assignment, `for`/`with`, walrus and unpacking all count. This does not infer
control flow. `source.own_scope`, shared with the binding collector, prevents
nested locals leaking into the enclosing function.

Hand-written documented method tables include only methods common to supported
Python versions. Runtime `dir()` would make results interpreter-dependent
([AD-7](ad-07-determinism-is-measured-not-assumed.md)). Literals resolve fully;
annotations resolve `partially_resolved`, because Python does not enforce them.

Self analysis found 703 unresolved calls out of 3,982 (17.65%); 621 (88%) were
stdlib/container/string/path/argparse receiver methods. Their noise affected
`calls_unresolved` and `unresolved_ratio` ratchets. This cut uses static bindings,
not general type inference. Call-result receivers, deep attributes
(`self.items.append`), subscripts and conflicting rebindings stay unresolved.

`ANALYZER_VERSION` rises for changed call records
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Checks: `tests/test_analyzer.py` covers each source, call results, absent methods
and plain or `for` rebindings. `tools/classify_unresolved.py` measured the self
change from 703/3,982 (17.65%) to 421/4,051 (10.39%).
