# AD-20 A level is its own contract, never a nesting inside one contract

Amended by [AD-111](ad-111-recursive-inside-contract-tree.md): mounted levels are followed
recursively in the root run, without requiring a separate configuration for each child.
Amended by [AD-112](ad-112-local-publication-at-each-boundary.md): child APIs stay local;
the public-surface equality and its mismatch diagnostic below are historical, not current policy.

Originally, each optional level had its own `archkeel.toml`, scan scope and contract,
with unlimited depth and no parent or child field in the component model.
Levels shared only an inside-contract reference, one upward measurement, checks for
matching `public` and inherited forbidden imports, and an observation record for
rendering ([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)).
`init` never opened another level itself.

A second level on `check` drafted 12 sub-components and 132 decisions, versus 30
pairs above. Closed-world coverage is per level; nesting it in one contract would
multiply decisions and require precedence. The same commands already worked on
`src/archkeel/check`, treating siblings as external packages.

Original checks: the shop's `store` inside passed both levels; catalog overlays
covered `inside.public_mismatch`, `inside.forbidden_import` and deletion producing
`contract.invalid` at `/components/1/inside`. A test prevented `init` from drafting
`inside`. Comparison of an inside `external_dependency_scope` with the parent
was not implemented.
