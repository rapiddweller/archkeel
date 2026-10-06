# AD-36 A rule the inside declares is recorded and carried, so the verdict it produces survives every command

Amended by [AD-110](ad-110-inside-rules-use-the-shared-evaluator.md) and
[AD-111](ad-111-recursive-inside-contract-tree.md): shared evaluation, revision-bound
contracts and provenance extend recursively through explicit inside levels.

At load time, namespace inside rules as `<parent>:<rule id>`, matching child names.
Declarations, violations and stable ids then share one identity. Projected rules
carry `parent_id`; `requires_declared` and `_decided_component_pairs` skip child
rules for outer decisions, while `agent_decisions` counts them.
`declaration_paths` includes `inside` so snapshots materialize locked contracts.
Inside violations point to `/components/<n>/inside`.

Previously, `requires_violations` referenced an unprojected
`STORE-REQUIRES-COMPLETE`. `trace_valid_violations` dropped it and validation
reported `observation.incomplete` instead of the import. Snapshots also omitted
inside contracts, making their locks unverifiable. The clean self-inside had
hidden both failures ([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)).

Bare ids can collide; renaming after construction duplicates identity and leaves
stable-id collisions; parsing ids to infer levels replaces explicit `parent_id`;
accepting missing rules would hide broken evidence chains.
Originally all inside rules were recorded but only `complete_requires` evaluated
([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)); inside
provenance docs were not carried. The amendments above remove those limits.

Checks: the shop's four-child `store` inside has three crossing edges. Removing a
requirement in `class-a-complete-requires-inside` yields three `rule.violated`
findings under `store:STORE-REQUIRES-COMPLETE` at `/components/1/inside`.
`class-a-decision-open` still reports its outer open pair, and protocol rows
verify locks over both levels.
