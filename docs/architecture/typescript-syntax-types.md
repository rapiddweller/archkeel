# TypeScript syntax port

The source component owns one frozen syntax DTO port and its nominal semantic domains.
The existing ten DTOs move from `parse.py` into `syntax.py`; parser objects never cross
that port. Only `parse.py` touches Tree-sitter and classifies its closed node vocabulary.
Unknown node kinds remain unknown and are still traversed; arbitrary text never becomes
a known syntax category merely because its spelling resembles one.

Collection consumes the shared nominal ReferenceForm, DefinitionKind, Visibility,
BaseRelationship, SiteKind, SiteUse and ReceiverKind domains. Resolution and inventory
states belong privately to the collector. Enum values are used to preserve emitted wire
data and stable ordering, rather than as a string comparison escape hatch.

One private `_node_kind(raw)` decoder classifies all closed node categories in the parser.
It returns an owned nominal category or None, with conservative unknown-node behavior.
Raw parser objects stay inside parse.py; the frozen syntax DTO port contains lexical data.
There is no node facade, per-parse identity map or cache-cleanup protocol.

Direct whole-module native comparison guards cover `parse.py`, `collect.py` and the
input-owning `syntax.py`, without exceptions. Independent authored Target intent pins seven semantic domains and eight
critical DTO fields, and actual source mutations are checked against fixed intent bytes.
Class/member names, field lookup keys and query-capture names remain open lookup data.

Reserved path/package-prefix and file-extension grammar remains explicitly tracked in
[the migration ledger](typescript-control-types.md) as the next coherent input-decoder
increment under #542. Native construct observations are bounded evidence, so this
increment does not claim complete grammar migration.

Valid direct construction through the old parser imports stays supported: each owning
frozen DTO normalizes only its own closed fields at construction. Invalid closed values
fail there; nominal field annotations remain narrow. Names and type annotations stay data.
The legacy omitted receiver category derives `this` or other from a supplied receiver;
an explicit parser-owned OTHER category is preserved even when the source text is `this`.

The direct decoder replaces the controlled cached candidate 3ba489 without changing the
syntax DTOs or the real collector wire facts. It preserves one classification owner when
read more than once; once-per-node caching is not required by the architecture contract.
A runtime and Python-allocation comparison records the cost of both nominal variants.
The original unmerged cached candidate's method-name candidates are not treated as proven
receiver types or semantic improvements when native call counts are compared.
