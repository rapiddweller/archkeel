# Typed compiler and resolver control

TypeScript configuration owns `ModuleKind`, `ModuleResolution` and `ScriptTarget`.
It converts accepted TSConfig values without regard to case, canonicalizes the legacy
`node` alias to Node10, and preserves diagnostics and partial coverage for invalid inputs.
`Options` exposes nominal enum fields and derived modes. A raw string passed directly
to that Python API is rejected rather than interpreted as a default.

Resolution owns `ModuleFormat` and `SourceKind`. Package type and export conditions
are decoded into private resolver enums once before dispatch. Unknown export conditions
still stop resolution, including when a later default would otherwise resolve.
`Format` remains an alias for `ModuleFormat`; it no longer denotes raw wire strings.
The collector consumes these types, including CommonJS require detection.

Configuration also owns the path/glob grammar shared by selection and resolution.
`PathToken` distinguishes punctuation and the reserved `node_modules` segment from
arbitrary supplied path names. Extension families and file shadowing have local owned
classifiers. Regular expressions parse export-target syntax; lookup tables classify
accepted compiler and extension vocabulary. Enum values are not compared as strings.

Python module visibility has no supported lexical proof and is not asserted by this
bounded Target. Public member visibility, exact types and named component ports remain
explicit requirements.

The own inner contract now separates syntax, configuration, resolution and collection.
Crossings use named APIs. An independently authored Target pins option fields, derived
return types and the resolver's format parameter/return. Native source mutations are
evaluated against unchanged contract bytes. Whole-module native construct rules protect
configuration and resolution, including parser/protocol dispatch, without allowances.

This completes those two modules. TypeScript syntax and collection still contain other
string-driven syntax categories; they are separate remaining migration work under #542.
Module names, file paths, JSON keys, diagnostics and emitted protocol bytes remain strings.
The existing pinned TypeScript 5.9.3 config corpus and compiler differential are unchanged.
