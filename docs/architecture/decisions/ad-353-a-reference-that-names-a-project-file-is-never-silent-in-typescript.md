# AD-353 A reference that names a project file is never silent in TypeScript

**Status.** Accepted. Issue #976, after the review of #974. It extends AD-274 and AD-352.

**Problem.** With a contract that forbids a -> b, three constructs gave PASS in the Python collector
and in the native one: `/// <reference types="../b/t" />`, `declare module "../b/t" {}` and
`self.x()` for a global that a script of b publishes as `window.x`.

**Decision.**
1. A `/// <reference types="...">` directive whose value starts with `.` or `/` is a concern, as a
   `path` directive is. A `types` name stays silent (AD-274).
2. A `declare module "..."` whose name starts with `.` or `/` is a concern,
   "Unobserved module augmentation: <name>". A bare name is not read: a `paths` alias could map it
   to a project file, and this stays a blind spot in `docs/known-limits.md`.
3. `self` is a root of the global object, like `window` and `globalThis`.
4. Both collectors change together, so the replies stay equal (AD-352). The native tests compare
   them on these constructs.
5. The JSDoc import reader moves from `parse.py` to `jsdoc_imports.py`, a module of the source
   component, so that `parse.py` shrinks. The count of unresolved calls rises from 986 to 987.

**Not done.** Bare-name augmentation. The 4 MiB file cap of the native collector stays a difference
(`docs/known-limits.md`).

**Check.** `tests/test_collector_false_pass_sources.py` gives the three constructs to both
collectors and expects no PASS; `tests/test_typescript_parse.py` and
`tests/test_collector_native_imports.py` hold the parity.
