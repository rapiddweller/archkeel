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

Cache cleanup belongs to the private `_Tree.clear()` port. Its `tree.clear()` call is
PARTIAL under the existing native analyzer: the method is a named internal candidate,
but the receiver's runtime type is unproven. The previous `tree.nodes.clear()` was
fully unresolved. Inside the owner, a declared dictionary receiver makes `dict.clear`
PARTIAL without claiming a runtime proof; the literal legacy receiver dictionary's
`get` call is resolved as `builtins.dict.get`. No observer authority is added.

The parser's nominal boundary has a measured runtime and memory cost. The independent
[H/NestJS comparison](https://github.com/rapiddweller/archkeel/actions/runs/38956060497)
uses 72 files (105,335 bytes), alternating seven rounds and Python 3.11.12. It compares
DTO contents after sorting only the already unordered import-binding collection.
On that runner, the median grew from 0.532 to 0.861 seconds and peak Python-tracked
allocation from 2.05 to 3.03 MB. The smaller temporary per-access decoder measured
0.825 seconds / 2.06 MB; it does not satisfy the selected once-per-node boundary.
These are runner measurements, not portable limits or a performance improvement.
