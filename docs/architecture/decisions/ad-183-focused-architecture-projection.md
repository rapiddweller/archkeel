# AD-183: Focused architecture projection

`report --only architecture --json` projects the authenticated shared report once.
The typed projection is the source for architecture fact sheets. It adds no collector,
policy evaluator or inferred ports. Required Target relationships, permissions and imports
remain separate. Nested ownership uses exact recorded scopes; ties remain UNKNOWN.

Component slices retain global verdicts, coverage, assessments, source identity and UNKNOWNs.
Finding IDs and recorded locations retain #314's format. A generic violation remedy shares
the existing diagnostic text. Command result schema 5 adds the projection; its own schema
starts at 1.0. Stable JSON excludes artifact paths.

The delegated task owner approved two new Governance modules and their exact public
projection symbols, plus `workflows -> declarations` to authenticate dependency
permissions against the recorded contract. This feature widens the contract.

Evidence: `tests/test_architecture_projection.py`. Own-repository byte budgets and integrated
gates are separate acceptance checks; no record is truncated to satisfy a size budget.
