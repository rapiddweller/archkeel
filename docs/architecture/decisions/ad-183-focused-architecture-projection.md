# AD-183: Focused architecture projection

`report --only architecture --json` projects the authenticated shared report once.
The typed projection is the source for architecture fact sheets. It adds no collector,
policy evaluator or inferred ports. Required Target relationships, permissions and imports
remain separate. Nested ownership uses exact recorded scopes; ties remain UNKNOWN.

Component slices retain global Core verdicts, coverage, source identity and UNKNOWNs,
plus governing ancestor rules/levels and peer ownership context. ID/scope/label collisions
produce a named diagnostic. Core and projection share the existing requires predicate;
Allow declarations do not bypass complete_requires or forbidden dependency constraints.
The architecture command envelope groups every UNKNOWN by exact kind, reason and scope
with counts. Only internal class/method/type Target details use Core summaries by scope,
kind, status and original reasons. Boundary relationships remain individual; the full
ArchitectureReport retains the detail source for #355. Authenticated namespaces shorten
names. Its generated schema defines reconstruction and defaults.
Finding IDs and locations retain #314's format and existing remedy text.
Command result schema 5 accepts this separate 1.0 envelope. Stable JSON excludes artifact paths.

The delegated task owner approved two new Governance modules and their exact public
projection symbols and the view dataclasses actually contained in that public DTO, plus `workflows -> declarations` to authenticate dependency
permissions against the recorded contract. This feature widens the contract.

Evidence: `tests/test_architecture_projection.py`. Own-repository byte budgets and integrated
gates are separate acceptance checks; no record is truncated to satisfy a size budget.
