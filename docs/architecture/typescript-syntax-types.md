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

Reserved path/package-prefix and file-extension grammar belongs to the shared
[source-input port](typescript-source-input.md). The parser consumes its filename
classification and retains conservative fallback behavior. Native construct observations
remain bounded evidence; this does not claim complete runtime grammar coverage.

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

The [controlled comparison](https://github.com/rapiddweller/archkeel/actions/runs/38958337346)
preserves all 72 parser DTO projections and the exact strictly decoded H/Nest SourceFacts
wire bytes against both 8eb and 3ba. Counted UNKNOWN record identities are unchanged:
30 type positions, 20 routes and 8 other records. Native unresolved calls move from the
actual predecessor's 917 to 913; moved existing calls are named individually.

On the same Python 3.11.12 runner, seven alternating rounds measured median parser cost
for 72 files / 105,335 bytes: original 0.415 s, cached candidate 0.676 s, direct decoder
0.642 s. Peak Python-tracked allocation was 2.05 / 3.03 / 2.06 MB respectively.
The direct version saves cache state and about 5% of parser time versus the cached trial;
it still costs about 0.227 s more than the original string-based parser on that corpus.
These are runner measurements, not portable limits or a performance claim versus 8eb.

The [complete call-site comparison](https://github.com/rapiddweller/archkeel/actions/runs/38963358892)
uses the same engine for both actual revisions and joins all 346 checked calls in changed modules to
zero-based AST positions, callee/argument structure and closure bindings. No relevant
site remains unmatched. Existing PARTIAL status, reason, targets and multiplicity are
unchanged, but the total rises from 2,450 to 2,454: the four global decoder map lookups
are PARTIAL with a RecordData.get name candidate, not a proven dict receiver or return.
The legacy receiver map is resolved to builtins.dict.get. Four removed raw text operations
account for UNRESOLVED 917 to 913; this tradeoff is not an overall resolution improvement.
All 58 counted UNKNOWN identities and checked data remain unchanged. No resolver
capability, accepted debt, allowance or ceiling is increased.
