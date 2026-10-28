# AD-260 Opt-in bundler mode for the TypeScript collector

**Decision.** `[scan] bundler = true` (boolean, optional, default false, TypeScript
only) lets the collector treat four things a bundler decides as known behaviour:

- A. A non-relative import that a tsconfig `paths` entry maps to a scanned source
  file is proven; the "Local alias runtime conditions are not proven" gap is not
  raised. `baseUrl`-only resolution is not a bundler alias and keeps the gap. So does
  a target a directory `package.json` decided, and a bare package found in `node_modules`.
- B. A package whose `exports` conditions or `typesVersions` the resolver does not
  model is an `ExternalPackageTarget` to that package. Only the resolver reasons
  marked `package_internal` convert. Exports shapes, patterns and target paths, a
  broken `package.json`, `#imports`, self-reference and blocked options stay UNKNOWN.
- C. Asset imports (`.css`, images, fonts, `?url`, `?raw`, `?inline`, `?worker`) and
  JSON modules are external edges to the reserved identity `bundler:asset`, also when
  a `paths` alias names the file. A bare-package asset is an edge to its package. The
  file must exist inside the installed package (`<node_modules>/<package>/<subpath>`,
  no `.` or `..` segment); otherwise "Unresolved module" stays. A `?query` only makes
  a non-source file an asset: `./w.ts?worker` stays "Unresolved module".
- D. An import a tsconfig `paths` entry maps to a file outside the scan roots is an
  external edge to the alias, only when the alias is a valid npm package name
  (`@obc/api-client`). `@/ext`, `baseUrl`-only matches (`tests/h`) and relative targets
  outside the roots keep their gap.

The switch is explicit (D1). It requires `moduleResolution: bundler` in the loaded
tsconfig (D2). Otherwise the collector stays in the default mode and records one gap,
"Bundler mode requires moduleResolution bundler", so the result is UNKNOWN. Package
exports are not emulated (D3). The mode lives in the collector; the specifier and
asset vocabulary live in `source_input.py` as enums. No module or contract changes
(D7). Without the key the output is byte-identical to before.

The mode is recorded as the resolution feature `bundler-mode-v1`, added only when the
mode is active (key set, tsconfig loaded, `moduleResolution: bundler`). It adds no
section or record; host evaluation accepts it beside every registered feature set.

The key travels as the optional `resolver.bundler` field of the collector request.
The encoder writes it only when true. The decoder rejects an explicit `false` and any
unknown field. `PROTOCOL_VERSION` is not bumped. A collector that does not know the
field rejects the request, which fails closed.

**Reason.** A resolver that is more permissive than the real runtime turns an
unresolvable import into a proven dependency. A tsconfig with `moduleResolution:
bundler` also describes libraries that `tsc` emits for Node, where the bundler
assumption is false, so permissiveness must be a human claim. The first-party
architecture depends on the package identity, never on the file a bundler picks inside
`node_modules`. An external edge is already what a resolution into `node_modules`
produces.

**Rejected alternatives.**
- An environment variable: hidden state outside the config digest.
- Auto-detection from `moduleResolution: bundler`: see the Reason.
- Emulating bundler conditions: it varies by bundler and claims an unverifiable file.
- A new target type or a protocol bump: `ExternalPackageTarget` already fits.
- `vite:asset`: the mode is not Vite-specific. `bundler:asset` cannot collide with an
  npm package, because a colon cannot occur in a package name.

**Limit.**
- The bundler's aliases (`vite.config.ts` `resolve.alias`) are assumed to equal
  tsconfig `paths`. ArchKeel does not verify this; a divergence yields a wrong local
  edge.
- Package `exports` and `typesVersions` are not read; the edge names the package.
- `bundler:asset` is a reserved identity that rules and the report show as a package.
- Asset suffixes are case-sensitive. Triple-slash and JSDoc-import concerns stay UNKNOWN
  (no bundler changes them).
- `exports` patterns and other rejected shapes stay UNKNOWN. An exported asset that exists is an edge to its package (#728).
- Asset existence is a probe, not a digested input, like the resolver's other probes.

**Check.** `tests/test_config.py`, `tests/test_typed_collector_protocol.py`,
`tests/test_protocol_uml_target.py`, `tests/test_typescript_resolve.py`,
`tests/test_typescript_source_input.py` and `tests/test_typescript_bundler.py`.
