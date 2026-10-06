# AD-24 The report opens a component without requiring a decision

The flow view opens a component's modules and imports from the same observation,
without a contract field. Without a declared inside, edges are observed, never
conforming. A recorded inside decides pairs between its sub-components
([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)).

The data already contained 142 module edges, 74 inside one component. Viewing them
needs no decision; deciding them requires a contract
([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)).
A module view can use `symbols` and `calls`, but about one call in five remained
unresolved, so it cannot prove every relation.
Check: the opened view renders from `architecture.json` alone.
