# AD-798: The closure of an installed package that the scan imports is read

Status: accepted. Part of #880. Closes #1529. It amends AD-488 point 4.

## Context
AD-488 point 4 keeps the code of an installed package outside the model. A package can import
project source by a relative path (`node_modules/local/index.js` with `import "../../src/b/t"`),
so a module that imports `local` depends on `b`. On main `28be993f7` seven forms gave PASS: a
package at the root or below a scan root with an owner manifest, `require`, a reach through a
second package, a type-only import, a `/// <reference path>` and a `typesVersions` package.
AD-488 rejected a gap for each bare import: it would make every project UNKNOWN.

## Decision
`collect/package_closure.rs` runs after the walk of the selected files.
1. **Entries.** Each installed file (a `node_modules` segment) that an import of the scan resolves
   to, with the module and the evidence of that import.
2. **Closure.** Each entry is parsed; its static imports (`import`, `export … from`, `require` and
   `import()` with a literal, `import x = require`) and leading `types` directives are resolved
   with the resolver of the run, from the installed file. A `path="…"` directive is read by its
   text and resolved from its own file; `declare module "…"` is read by its text when its name is
   relative, or when the project sets `paths` or `baseUrl`. An installed source file joins the
   closure; a builtin and a name that resolves to no file are no step.
3. **Repaired file.** When the parser repairs a part, each quoted text after `from`, `import`,
   `import(` or `require(` is read as a name too.
4. **Undecided package.** When the resolver cannot decide a bare name (`typesVersions`) and the
   `node_modules` search finds an installed directory (also `@types/<name>` for a type reference),
   each source file of that directory joins the closure, without its nested `node_modules`.
5. **Reach.** A name that resolves to a file whose real path has no `node_modules` segment, another
   undecided name, and an unreadable installed file reach project source, and so does each file
   whose imports reach one. Each entry that reaches project source gives its importing module the
   gap `Installed package can reach project source: <entry> through <file>: <project file>`.
6. **Budget.** A closure of more than 20 000 installed files is a gap of each entry.

## Soundness
- Node and the compiler load package code only through these forms from the resolved entry, so the
  closure holds each file that the package can load statically.
- A workspace link (`node_modules/x` to `packages/x`) resolves to its real path: project source
  that the walk reads already, and no entry.
- An undecided name can name any file of its installed directory (point 4) or, outside one, any
  file (point 5). The text reading over-matches: a quoted name in a comment is read too.

## Truth
Node 26 loads the file of `b` for each runtime form (root, below a root, `require`, a second
package). TypeScript 5.9.3 (`tsc --listFiles`, `include: ["src/a"]`) adds `src/b/t.ts` for the
type-only import, the path directive and the `typesVersions` package.

## Price
No PASS turns UNKNOWN: graphql-js v16.15.0 1/0/7 with 67 gaps, and the fixtures F, H, H-uml and
L-nest are unchanged. None holds an installed `node_modules`, so a Next.js 13 application with
532 pnpm packages (883 MB) was measured: gaps equal to main, 4 s against 1 s. A first version gave
it 146 false gaps (path directives of `@types/react` and `next`, `typesVersions` of `@types/node`,
three repaired declaration files); points 2 to 4 remove them.

## Open
- A computed import inside a package (`require(name)`) is a reach since AD-812 (#1749).
- A package that a tool loads without an import of the scan: read when a repository data file names it (AD-830, #1750).
- A bare `declare module "x"` without `paths` or `baseUrl` is an ambient module, as in the scan.

## Tests
`tests/test_cli_native_installed_source.py`: 8 forms that must not PASS (7 give PASS on main), and
3 that keep PASS (a builtin and another package, a path directive to an own file, a package that
no import reaches). `native/typescript/src/package_closure_tests.rs`: the text reading.
