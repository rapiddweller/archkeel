# AD-353 A reference that names a project file is never silent in TypeScript

**Status.** Accepted. Issue #976, after the review of #974. It extends AD-274 and AD-352.

**Problem.** With a contract that forbids a -> b, three constructs gave PASS in the Python collector
and in the native one: `/// <reference types="../b/t" />`, `declare module "../b/t" {}` and
`self.x()` for a global that a script of b publishes as `window.x`.

**Decision.**
1. A `/// <reference types="...">` directive whose value starts with `.` or `/` is a concern, as a
   `path` directive is. A `types` name stays silent (AD-274).
2. A `declare module "..."` whose name starts with `.` or `/` is a concern,
   "Unobserved module augmentation: <name>". A bare name without `*` is a concern too when the file
   is a module file and the project sets `paths` or `baseUrl`: tsc resolves the name like an
   import, and the resolver is not asked (the cheaper sound choice). A wildcard name stays silent.
3. `self` and `frames` are roots of the global object, like `window` and `globalThis`.
4. Both collectors change together, so the replies stay equal (AD-352). The native tests compare
   them on these constructs.
5. The JSDoc import reader (`jsdoc_imports.py`) and the augmentation names (`augmentations.py`)
   move out of `parse.py`, into modules of the source component, so that `parse.py` shrinks. The count of unresolved calls rises from 986 to 987.

**Not done.** Sending a bare augmentation name through the resolver, so that only a name that lands
on a project file is a concern. `top`, `parent` and `window.window.x`. The 4 MiB file cap of the native collector stays
a difference (`docs/known-limits.md`).

**Check.** `tests/test_collector_false_pass_sources.py` gives the three constructs to both
collectors and expects no PASS; `tests/test_typescript_parse.py` and
`tests/test_collector_native_imports.py` hold the parity.
