# AD-812: A loader with an unknown target in an installed package withholds its routes

Status: accepted (lead decision 2026-11-17, the way of Python #1519). Part of #880. Closes #1749.
It amends AD-798.

## Context
AD-798 reads the static imports of each installed package that the scan reaches. A computed
`require(name)` or `import(path)` in such a package was not read: `node_modules/local/index.js`
with `require("../../src/b/" + "t")` loads project source, so a module that imports `local`
depends on `b`, and main `5e023fda0` gave PASS. A statement in a decision record does not accept a
false PASS.

## Decision
In each runtime file of the closure (`collect/package_closure.rs`, `unknown_loader`), a loader whose
target is no literal is a reach of project source:
1. a `require`, `import()` or `import x = require` whose argument the parser reads as no plain
   string;
2. a call `createRequire(`;
3. in a file that the parser repaired, each `require(` or `import(` whose argument is no quoted text.
The gap of AD-798 names the entry, the file and the loader: `Installed package can reach project
source: <entry> through <file>: a loader with an unknown target (computed require at line 2)`.
A declaration file loads nothing at run time, and a type-level `import()` names a literal, so a
declaration file has no such loader.

## Soundness
The loader can receive any text at run time, also the path of a project file, so the routes from
the package are withheld; the gap holds each module whose import reaches the file. A loader that
the text does not show (`module.require`, `eval`) stays outside this rule.

## Price
No PASS turns UNKNOWN on graphql-js v16.15.0 and the TypeScript fixtures F, H, H-uml and L-nest
(none holds installed packages). The Next.js 13 application of AD-798 (532 pnpm packages) gets one
gap: a test module imports `vitest`, whose `vite-node/dist/client.cjs:354` loads test files with
`require(t)`, which is true. A first version that read the text `createRequire` in declaration
files gave 74 gaps there.

## Tests
`tests/test_cli_native_installed_source.py`: a computed `require`, a computed `import()` and
`createRequire` give UNKNOWN (each gave PASS on main); a declaration file that declares
`createRequire` keeps PASS.
