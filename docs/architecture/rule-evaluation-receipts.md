# Core evaluator receipt facets

The existing governance model owns the optional typed view of the existing rule_evaluation receipt. Presence identifies this single subset; two boolean facets retain assessment and cycle-scope completeness. Generic Record.kind remains an open string and arbitrary record data remains opaque.

Omitted assessment_complete retains the established true default. Omitted cycle_scope_complete remains false. Present values count as complete only when they are exactly true. No missing, invalid or future metadata is promoted into evidence.

Core rule_support and UML evaluation retain issuance. The shared marker is serialized as the same plain string. Readers retain original identity, subjects, rule IDs and proof payloads. A comparison-bearing UML record with the wrong kind, rule identity or stable ID still causes the existing hard diagnostic.

The native raw-control guard covers only the new receipt reader. Eight existing selection sites use its optional facet; unrelated control vocabularies in those callers are outside this bounded increment. No source-facts policy, wire schema, resolver authority, baseline ceiling or metadata artifact changes.
