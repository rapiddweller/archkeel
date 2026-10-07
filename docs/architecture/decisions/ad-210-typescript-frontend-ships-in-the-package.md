# AD-210: The TypeScript frontend ships in the Python package

Use tree-sitter inside `archkeel.analyzer.typescript`, replacing AD-150's npm collector.
One Python installation covers all three languages; analysis needs no Node runtime and
executes no project code. The existing process boundary retains timeout and output limits.

Only `parse` imports tree-sitter. `config` reads snapshot configuration, `resolve` resolves
specifiers, and `collect` assembles SourceFacts. Core owns verdicts; the shared graph, Target
comparison and renderer own UML. AD-151's dependency rules remain in force.
Pinned grammar identity participates in runtime provenance.

`inner-uml-v1` supplies lexical declarations, member inventories and relationship sites.
It enables no Python-only proofs. Incomplete import and inner-UML evidence retain separate
UNKNOWN assessments; file coverage never proves a complete symbol inventory.
Package-based `extends`, `exports`, `typesVersions`, project references and unsupported
settings or syntax remain gaps. This frontend is not a type checker.

Frozen adapter and compiler references guard the modeled cases, not compiler parity.
Demos and compatibility limits live in [the TypeScript guide](../typescript-demo.md).

Alex accepted 715 unresolved self-calls on 2026-10-07 after a bounded sample fixed 12 of 727.
The scan covers `src/archkeel`, including the Python TypeScript frontend. Other budgets stay
unchanged; the [amendment](ad-210-typescript-package-amendment.json) binds this decision.
