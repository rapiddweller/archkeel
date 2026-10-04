# AD-153 Unproven chains retain declared signatures

Property chains left direct evaluation before effective-class proof. When that proof failed,
six visible source positions could collapse to one inherited UNKNOWN (#306).

Keep the aggregate limit and retain individually evidenced declared candidates. They carry
raw annotations, `signature_scope: declared` and UNKNOWN effective binding. They produce no
runtime violation, proven exposed type or allowance. A base hook can replace the descriptor;
restoring unconditional lexical FAIL would be unsound.

Reuse the existing unique class index and signature reader. Ambiguous or nested owners cannot
borrow another class's source evidence. A proven final plain binding suppresses earlier chains.
Private names, overload implementations, effective replacements and scope exemptions stay unchanged.

Reports show lost decision coverage explicitly. Six declarations plus the aggregate limit
mean seven UNKNOWN positions, not seven active accessors. Existing budgets can reject that
increase. Direct signature policy and exit policy remain unchanged.

Core observation version becomes `0.69.0`; the open payload gains optional scope detail.
Formats and source collection are unchanged. Reobserve before comparing changed checker identities.

`tests/test_owned_property_candidates.py` covers report, full validation, canonical round-trip,
HTML, re-exports, source identity, scopes and annotations. Existing property/transport controls
retain proven chains and reject missing or malformed proof.
