# TypeScript syntax: prefer one direct nominal decoder over a cached node facade

Decision checkpoint before changing the controlled source candidate.

User intent is one owned parser boundary, nominal closed domains, conservative unknown
nodes, clear component APIs and less code. It does not require once-per-node decoding.
Keep parse.py as the only Tree-sitter owner and syntax.py as the existing moved DTO port.
Keep all valid legacy DTO normalizers, independent authored Target fields and five native
whole-module guards from the reviewed candidate. Preserve explicit unknown receiver OTHER.

Replace private _Tree/_Node wrappers with one _node_kind(raw: _RawNode) -> _NodeKind | None
function. Every syntax dispatch consumes its nominal result. Keep raw nodes inside parse.py.
Repeated reads use the same canonical private classification table; no second vocabulary,
new observation authority, identity cache, cleanup protocol or artifact framework is added.
Remove only the tests that assert the discarded cache/once-per-node implementation.
Keep unknown-member, unknown-receiver, real parser and real DTO->collector/wire controls.

The controlled comparison is 3ba489e4019950c24edc974bb3242620704c5b34. The actual product
predecessor is 8ebc1da53b3ac7290f78978d5e69e4f3c59185c3 with calls_unresolved=917.
Never use the unmerged 863 candidate as the before baseline. The adapter gave raw external
calls internal method-name candidates; losing those PARTIAL candidates is not a semantic
TypeScript regression. Measure and name all remaining calls, compare exact UNKNOWN positions
and routes, and accept no call limit above the existing 917 or added debt/allowances.

Before a final candidate: preserve a concrete minimal source diff; run parser and legacy DTO
controls, all native authored-Target/guard mutations, all 28 compiler differentials, exact DTO
and real SourceFacts wire comparisons, semantic UNKNOWN identities/routes, calls and runtime/
Python-allocation measurements. Generate a normal v2 receipt against exact 8eb and verify the
exact committed final ref without --write-amendment. Independent Astra review remains required.
Do not begin another input feature before full regressions are green.

The previous native REDs for the same nominal API/guard behavior remain applicable:
38941278973, legacy DTO consumers 38953133960 and syntax owner guard 38954505385.
This is a controlled implementation replacement, not a new public behavior.
