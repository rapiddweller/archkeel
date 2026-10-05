# AD-202: Focused architecture projection

`report --only architecture --json` projects the authenticated shared report once.
The typed projection is the source for architecture fact sheets. It adds no collector,
policy evaluator or inferred ports. Required Target relationships, permissions and imports
remain separate. Nested ownership uses exact recorded scopes; ties remain UNKNOWN.

Component slices retain global Core verdicts, coverage, source identity and UNKNOWNs,
plus authentic Core rule declarations/assessments at governing ancestor levels and
all levels mounted in the selected subtree, with peer ownership/public/planned context.
Required wiring touching that same subtree is retained before detail/summary partitioning.
The native rule catalogue owns membership;
the projection has no separate policy catalogue. Allowed means a declared conditional
component permission; each import must satisfy every applicable rule. ID/scope/label collisions
produce a named diagnostic. Core and projection share the existing requires predicate;
Allow declarations do not bypass complete_requires or forbidden dependency constraints.
The architecture command envelope groups every UNKNOWN by exact kind, reason and scope
with counts. Only internal class/method/type Target details use Core summaries by scope,
kind, status and original reasons. Boundary relationships remain individual; the full
ArchitectureReport retains the detail source for #355. Authenticated namespaces shorten
names. Its generated schema defines reconstruction and defaults.
Finding IDs and locations retain #314's format and existing remedy text.
Rule assessments live in the shared graph vocabulary to avoid a model/projection cycle; model re-exports preserve existing imports.
Command result schema 5 accepts this separate 1.0 envelope. Stable JSON excludes artifact paths.
Ordinary reports carry the same Core projection for the human view; ordinary JSON keeps its existing null field. Component layers come from authenticated intent.

The delegated task owner approved two new Governance modules and their exact public
projection symbols and the view dataclasses actually contained in that public DTO, plus `workflows -> declarations` to authenticate dependency
permissions against the recorded contract. This feature widens the contract.

Evidence: `tests/test_architecture_projection.py`. Own-repository byte budgets and integrated
gates are separate acceptance checks; no record is truncated to satisfy a size budget.

Fresh native Self measured 99,057 bytes for the whole command envelope and 56,556 bytes
for the largest of 29 component ID slices. The owner superseded the proposed 50 KB/5 KB
limits with 160 KiB/80 KiB guards to retain complete governing records, assessments,
UNKNOWNs, locations and remedy. The regression reuses the shared native Self run and
encodes every envelope twice; the tiny fixture's size check is separate evidence.
This budget proof does not accept outstanding baseline changes or the release gates.
