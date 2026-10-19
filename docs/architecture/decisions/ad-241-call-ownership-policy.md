# AD-241: Call ownership follows bound declarations

Import permission does not decide invocation ownership. Name-only matches confuse
unrelated methods. Start with one owner policy; arguments and guards remain separate.

Contract 3.7 adds `call_owner`: `source`, one canonical `target`, `allowed_sources`
(scope prefixes) and `exact_sources` (exact module/function scopes, not file globs).
Existing rationale, provenance and decision fields remain required.

The rule rejects a bound invocation of the target outside those callers.
An unrelated bound method with the same name passes. Every selected, non-exempt
call must have an exact-target proof, a proven disjoint target or UNKNOWN.
An empty candidate list cannot establish disjointness. A known violation remains
FAIL beside uncertainty. An exact module allowance covers its own functions,
not child modules; an exact function allowance covers only that function scope.
Missing/empty/unreadable sources or an unobserved target cannot certify a receipt.
Root and mounted rules share one evaluator. No import permission changes.

The call observer adds optional, validated `CallBinding` evidence to existing
call records, with nominal `CallBindingOrigin` and one canonical target.
Initial origins are direct lexical bindings to scanned declarations and declared
receivers. Construction requires a later bounded extension.
Function source identity reuses the existing fixed-point owner exposure/transfer
result; the broader member-escape set also includes ordinary calls and cannot
prove that a provider binding was replaced. Missing exposure measurement is UNKNOWN.
Every call carries a proof or explicit null, with source/declaration evidence.
Completion requires the capability, complete inventory and per-call consideration;
the rule receipt cites all selected call
IDs and the native source/scope/digest binding. A global capability alone cannot
certify it. Each receipt binds its complete claim and observation schema version
to that inventory. Copying a receipt to another rule/scope, changing its claim or
downgrading the observation version cannot retain a proven assessment. Re-observe
pre-release artifacts containing only a shared inventory proof; saved readers keep
them UNKNOWN. This binding detects inconsistent evidence, not artifact authenticity.
Legacy observations without these facts remain UNKNOWN for this
new rule only. Existing call-graph candidate status and old-rule receipts are
preserved; candidates alone never prove ownership.

Declared receivers bind one scanned class/protocol through a plain parameter
annotation. This proves a declared static boundary, not runtime conformance or
execution. Rebinding, ambiguous annotations and unresolved members remain UNKNOWN.
Direct calls include import aliases. External targets, stored members, constructors
and inherited surfaces need separate negative controls. No identity from suffixes.

Reuse existing lexical scopes, definition identities and type syntax. Shared
import-binding helpers belong to the source/scopes owner; collector peers do
not import one another. Source facts contain identity/evidence, never allowed
callers or policy verdicts. Policy and receipts belong to Core evaluation.

New observations use wire schema 2.1 and observer 0.75. New decoded profiles and
command-result9 add call-binding evidence; command schemas6/7/8 retain their version
boundaries. Current readers strictly admit known binding origins and shapes.
Older readers must reject them: 4.0.1 otherwise silently omitted call-owner assessments, including known
violations. Historical 1.2/1.3/2.0 report bytes remain readable by the new reader;
Delta comparison still requires the same schema, analyzer and contract.
Older contracts reject the new rule; unsupported profiles cannot certify it. Optional
fact payloads must validate their exact typed shape and evidence references.
Do not weaken another source field or relabel runtime resolution as proven.
Core reuses the canonical version-feature API through three explicit IR exports;
later versions must keep earlier capabilities without another version inventory.

Acceptance starts with allowed Storage paging, forbidden callers and
an unrelated same-named method. Add direct/aliased/relative calls, lexical and
member mutation, missing scope, stale/missing capabilities, mounted rules and
known FAIL beside UNKNOWN. This slice does not retire any EE checker until
its full supported forms and installed-release evidence are equivalent.

Native verification tightened the original 837 unresolved-call ceiling to 832.
The canonical baseline remains authoritative; the 52 typing-position ceiling remains.
Closed attribute scopes for `CallOwnerRule` and `CallBinding` remain strict;
required positions need positive proof, with no additional UNKNOWN allowance.
The [shared amendment](compact-target-amendment.json) binds this target together with
the three explicit version-API exports. This does not prove EE checker equivalence.
