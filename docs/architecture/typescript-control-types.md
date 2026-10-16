# Typed compiler and resolver control

TypeScript configuration owns `ModuleKind`, `ModuleResolution` and `ScriptTarget`.
It converts accepted TSConfig values without regard to case, canonicalizes the legacy
`node` alias to Node10, and preserves diagnostics and partial coverage for invalid inputs.
`Options` exposes nominal enum fields and derived modes. A raw string passed directly
to that Python API is rejected rather than interpreted as a default.

The shared source-input port owns `ModuleFormat` and `SourceKind`; resolution retains
identity reexports for existing consumers. Package type and export conditions
are decoded into private resolver enums once before dispatch. Unknown export conditions
still stop resolution, including when a later default would otherwise resolve.
`Format` remains an alias for `ModuleFormat`; it no longer denotes raw wire strings.
The collector consumes these types, including CommonJS require detection.

The [source-input port](typescript-source-input.md) owns the shared path/specifier and
filename grammar. `PathToken` distinguishes punctuation and the reserved `node_modules`
segment from arbitrary supplied path names. One nominal suffix classifier owns source,
format, declaration, substitution and shadowing metadata. Unsupported suffixes remain
unknown; absence has the separate `FileSuffix.NONE` value. Snapshot bookkeeping uses
canonical IR `ResolutionRole` values and normalizes valid legacy roles when read.
Package export-target syntax stays with resolution; compiler glob expansion stays with
configuration. Enum values are not compared as strings.

Python module visibility has no supported lexical proof and is not asserted by this
bounded Target. Public member visibility, exact types and named component ports remain
explicit requirements.

The own inner contract now separates syntax, configuration, resolution and collection.
Crossings use named APIs. An independently authored Target pins option fields, derived
return types and the resolver's format parameter/return. Native source mutations are
evaluated against unchanged contract bytes. Whole-module native construct rules protect
configuration, resolution, syntax parsing and collection for the native
equality/membership/match/alias observation scope, without allowances. This is a bounded measured guard, not proof that every grammar
entry point has already been converted into a nominal domain.

The source-input increment addresses the twenty measured TypeScript prefix/suffix sites
in configuration, resolution and collection, plus their computed/dynamic suffix consumers.
Native checks cover actual source and fixed API type intent; the independent Dart inventory
is a separate increment. A bounded construct guard does not prove every runtime string
operation safe or infer a parser capability it does not observe.

Open user-supplied prefix/suffix matching (for example `_best_pattern`) remains an operation
on data. Module names, file paths, JSON keys, diagnostics and emitted protocol bytes remain
strings. The existing pinned TypeScript 5.9.3 config corpus and compiler differential are
unchanged. No `startswith(ENUM.value)` rewrite or new source/form allowance is completion.
