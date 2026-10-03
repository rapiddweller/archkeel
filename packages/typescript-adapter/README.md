# Archkeel TypeScript source adapter

A separate, pinned TypeScript 5.9.3 Compiler API process. Reads one collection
protocol 1.0.0 request on stdin and writes one SourceFacts response on stdout.
Errors go to stderr with nonzero exit. It never runs project code or installs tools.

Development: Node 26.3.1 / npm 11.16.0. Runtime: Node 22.13+, 24, or 26+.

```sh
make install
make verify
make pack
node dist/entry.js < request.json > facts.json
```

The snapshot root, source roots, namespace, and tsconfig come from the request.
Only source observations cross the process boundary; policy stays in Core.

The import profile collects static imports, reexports, import types, literal
`import()`, import-equals, and unshadowed CommonJS `require`. It follows local
TypeScript and JavaScript dependencies inside the selected roots, including
runtime `.cjs` beside `.d.cts`. Declaration and runtime targets remain distinct.
Paths include extensions in the collision-free module identity.

Computed or unproven imports, syntax/config errors, missing runtime sources,
out-of-scope local dependencies, project references, and preserved symlink lookup
contexts produce UNKNOWN gaps.
Indirect `module.require` references and calls also remain UNKNOWN.
Resolved external package identities require digested resolver inputs inside the
supplied snapshot. Missing or outside-snapshot inputs remain UNKNOWN. Resolver
files are digested separately from selected graph files. Function calls, symbol-level
semantics, state, and type-shape measurements are not supported by this profile.
