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
configuration and resolution for the native equality/membership/match/alias observation
scope, without allowances. This is a bounded measured guard, not proof that every grammar
entry point has already been converted into a nominal domain.

Remaining migration under #542 is explicit:

- `parse.py` and `collect.py`: Tree-sitter node kinds, semantic syntax DTO fields and
  collector resolution/inventory states; move the existing DTOs into one named syntax port.
- `config.py`: relative-parent detection in `is_outside`, relative `extends` input in
  `_extended`, root-prefix parsing in `_base_path`, terminal deep-glob parsing in `_discover`,
  and source/extension classifiers in `_supported` and `_shadowed`.
- `resolve.py`: reserved `node:` in `is_builtin`, scoped `@` names in `package_name` and
  `_typed_name`, `#` package imports in `resolve`, trailing directory syntax and source/format
  extension parsing in `_strip_extension`, `_file_paths`, `format_of`, `_mapped` and `_worker`.

Reserved grammar and protocol prefixes need an owned entry decoder followed by nominal
consumption. Open user-supplied prefix/suffix matching (for example `_best_pattern`) remains
an operation on data. No `startswith(ENUM.value)` rewrite or new exception is completion.
Module names, file paths, JSON keys, diagnostics and emitted protocol bytes remain strings.
The existing pinned TypeScript 5.9.3 config corpus and compiler differential are unchanged.
