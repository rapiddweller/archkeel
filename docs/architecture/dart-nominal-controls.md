# Dart nominal control boundaries

The Dart Python implementation separates immutable syntax values from parsing.
`syntax.py` owns the existing DTOs and finite semantic categories; `parse.py`
retains compatible DTO reexports and owns Tree-sitter extraction. A private
parse-local node view decodes each raw node kind once, caches identity within
one tree, and continues traversing unknown grammar nodes.

`resolve.py` consumes nominal syntax categories and owns resolution outcomes
and its extra binding roles. Snapshot SDK state reuses the canonical
`ir.facts.RuntimeRequirementState`; it does not declare a second SDK vocabulary.
Names, paths, excerpts and externally meaningful diagnostic text remain data.
URI, root, YAML scalar and Dart string escape recognition remain real grammars.

The inner Dart contract publishes named APIs and authors nominal field and
resolver return intent independently of observation. Whole-module Python
implementation guards cover syntax, parser, resolver, snapshot and collection;
this does not claim Dart-project `forbidden_construct` capability.

Native tests mutate actual source against unchanged Target intent. SDK-free,
directive, resolver, false-positive, UML acceptance and Compass demo tests
remain the behavior oracle. No exception or increased debt allowance is added.

Builtin URI classification belongs to resolution. The existing ResolvedTarget
carries its binary builtin flag to collection, which does not inspect the URI
scheme a second time. Local/external package/alias resolution remains unchanged.
