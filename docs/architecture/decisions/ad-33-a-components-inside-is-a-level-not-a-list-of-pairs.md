# AD-33 A component's inside is a level, not a list of pairs

Use `requires` at each inner contract level instead of an exhaustive module-pair inventory. The
architect chooses which responsibility boundaries need a level; size observations alone do not
create policy. An omitted requirement list still leaves intent open.

This replaces [AD-31](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md) and reuses
[AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md) within
[AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)'s scoped contracts.
