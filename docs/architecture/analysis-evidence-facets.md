# Owned analysis evidence facets

Part of #542: use the actual semantic owner rather than a global Record-kind enum.
Facts owns supported collector signal/gap tags and the imports/signature uncertainty
dimension. Model owns Core-generated boundary/coverage/allowance evidence and the
member-inventory replay marker. Authored declarations, topology and SourceSymbolKind
stay separate. Scalar readers return a nominal known value or None for unrelated/future
data; generic Record.kind remains str. Recognition alone never grants proof authority.

Keep SOURCE_RESOLUTION_GAP_KIND and MEMBER_INVENTORY_PROOF compatibility strings derived
from the one canonical member, serialize real wire text at existing writer boundaries,
and retain all module/evidence/subject/ID and inventory replay validation.
Preserve absent/null/default behavior. The existing legacy imports and scope limitations
remain. Native fixed Target/mutation evidence protects real reader input/return types
and decoder control; producer/Core parity plus final current-source audit verifies readers.
