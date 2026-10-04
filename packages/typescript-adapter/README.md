# Archkeel TypeScript source adapter

A separate, pinned TypeScript 5.9.3 Compiler API process. Reads one collection
protocol 1.0.0 request on stdin and writes one SourceFacts response on stdout.
Errors go to stderr with nonzero exit. It never runs project code or installs tools.

Development: Node 26.3.1 / npm 11.16.0. Runtime: Node 22.13+, 24, or 26+.
The response declares this requirement from package engines and leaves construct
support empty; Core owns runtime checks and unsupported-rule refusal.

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
An existing explicit `.js`, `.mjs` or `.cjs` runtime is observed even when the
compiler substitutes TypeScript source. Type-only `node:` aliases use compiler
resolution; Node value imports retain their builtin identity.
Paths include extensions in the collision-free module identity.

Computed or unproven imports, syntax/config errors, missing runtime sources,
out-of-scope local dependencies, project references, and preserved symlink lookup
contexts produce UNKNOWN gaps.
Indirect `module.require` bindings and Node loader factories remain UNKNOWN,
including erased TypeScript wrappers. Known Node module namespaces used through
`.then` or unproved value escapes also retain a gap, including calls, literal
containers, returns and reassignment. Direct member use and proven aliases remain
supported, including known `Module` and `default` exports. Namespace rest, nested
export bindings and default initializer escapes stay UNKNOWN; type-only references
create no value gap.
Local value exports retain loader identity. Direct Node loader-bearing reexports,
namespace and star exports stay UNKNOWN. Explicit type-only exports and local
exports of proven type-only imports remain supported.
Local value aliases and non-explicit CommonJS targets remain UNKNOWN, including
extensionless, dotted-stem and directory specifiers. Compiler resolution alone
cannot prove the runtime target; runtime_file stays null.
Direct CommonJS loads of explicit JavaScript need the physical runtime file;
missing files stay UNKNOWN. Static TypeScript imports keep compiler semantics.
Resolved external package identities require digested resolver inputs inside the
supplied snapshot. Missing or outside-snapshot inputs remain UNKNOWN. Resolver
files are digested separately from selected graph files. Function calls, symbol-level
semantics, state, and type-shape measurements are not supported by this profile.
