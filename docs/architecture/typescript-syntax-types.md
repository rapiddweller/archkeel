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

A private node identity map decodes each raw kind once during one parse. Immutable span
and error metadata are captured with it. A `finally` block clears the map on every exit,
including decoder failure; parser objects and cache state do not escape in the DTOs.

Direct whole-module native comparison guards cover `parse.py` and `collect.py`, without
exceptions. Independent authored Target intent pins seven semantic domains and eight
critical DTO fields, and actual source mutations are checked against fixed intent bytes.
Class/member names, field lookup keys and query-capture names remain open lookup data.

Reserved path/package-prefix and file-extension grammar remains explicitly tracked in
[the migration ledger](typescript-control-types.md) as the next coherent input-decoder
increment under #542. Native construct observations are bounded evidence, so this
increment does not claim complete grammar migration.
