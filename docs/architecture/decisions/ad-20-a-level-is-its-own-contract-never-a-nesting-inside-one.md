# AD-20 A level is its own contract, never a nesting inside one contract

Amended by [AD-111](ad-111-recursive-inside-contract-tree.md): mounted levels are followed
recursively in the root run, without requiring a separate configuration for each child.
Amended by [AD-112](ad-112-local-publication-at-each-boundary.md): child APIs stay local;
the public-surface equality and its mismatch diagnostic below are historical, not current policy.

Depth is unlimited and
always optional: a component's inside is described by its own `archkeel.toml` with its own scan
scope and its own contract, and the component model gains no parent or child field. Levels are tied
together by four things only: a contract field that names the contract describing a component's
inside, one measured number reported upward for that component, two checks, namely that both
levels declare the same `public` interface for it and that nothing inside imports what the level
above forbids, and the record of a declared inside in the observation, so the report can draw the
inside without opening a second contract while rendering ([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)). `init` never opens a second level by itself. Reason: a second level on `check` drafted
12 sub-components and asked for 132 decisions, four times the 30 pairs of the whole top level,
because closed-world coverage applies per level; nesting inside one contract would multiply that set
and would need a precedence rule between levels. The mechanics already work without a model change:
the same commands run on a scope of `src/archkeel/check`, where sibling components appear as external
packages. Check: the shop sample declares an inside for `store` and passes on both levels;
`inside.public_mismatch` and `inside.forbidden_import` are each catalogued with an overlay that
replaces that contract, a third row deletes it and reads `contract.invalid` at
`/components/1/inside`, and a test holds `init` to drafting no component carrying `inside`.
An `external_dependency_scope` declared inside is not yet compared against the level above.
