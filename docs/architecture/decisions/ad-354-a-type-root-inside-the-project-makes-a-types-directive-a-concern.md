# AD-354 A type root inside the project makes a `types` directive a concern

**Status.** Accepted, 2026-11-11. Issue #988. It amends AD-274 rule 3.

**Problem.** AD-274 reads `/// <reference types="b" />` as a `types` entry that only adds globals.
With `typeRoots: ["./src"]` the name `b` is the directory `src/b` of the project, and its
`index.d.ts` declares names (`declare var fromB`) that rule 2 proves with no edge. A file of `a`
could use `fromB`, and the scan gave PASS for a rule that forbids a -> b.

**Decision.**
1. A `typeRoots` entry whose text has no `node_modules` may lie inside the project. The Python
   collector keeps this as `Options.project_type_roots`, the native one as the same field.
2. When any such entry exists, a `/// <reference types="name" />` directive is a concern,
   "Unobserved triple-slash reference: name", as a `path` directive is. The scan stays UNKNOWN.
3. Without such an entry, rule 3 of AD-274 holds: a `types` name is silent. A `types` directive
   whose value starts with `.` or `/` is a concern in every project (#976).
4. `/// <amd-dependency path="x" />` is a concern as a `path` directive is. A form without `path`
   (`name=`) is not.
5. `top` and `parent` stay no roots: they are the window only outside a frame. A use through them
   gives no edge and no gap; `docs/known-limits.md` says so.

**Reason.** A concern costs one UNKNOWN in the rare project that sets a project type root and names
a type package by `types`. A silent PASS hides an edge.

**Rejected.** An edge to the type root directory: the reply has no module for a directory, and
the snapshot cannot do the `types` lookup of a package. Reading the entry against the directory
of its tsconfig: the check is lexical and over-approximates, which is the safe side.

**Not done.** `compilerOptions.types` is a list of the project, not a directive of a file, and this
note does not read it.

**Check.** `tests/test_collector_false_pass_sources.py` (the probes `amd-dependency` and
`type-root-in-the-project`), `tests/test_typescript_parse.py` and
`tests/test_collector_native_augmentations.py` (parity of the two collectors).
