# AD-36 A rule the inside declares is recorded and carried, so the verdict it produces survives every command

Three things follow from it. An inside contract is renamed once as it is loaded,
each of its rules under `<parent>:<rule id>` the way a sub-component already is, so the projected
declaration, the violation and the id that violation is filed under are all built from the name
they will be read by, rather than corrected afterwards. A projected rule carries the
`parent_id` of the component holding it, and the derivations that decide *this* level's pairs,
`requires_declared` and `_decided_component_pairs`, skip a record that carries one, while
`agent_decisions` counts it: whose decision a rule is and which level it governs are two different
questions. And `declaration_paths` names each component's `inside`, so a `check` snapshot
materialises the contracts the lock was written over. A violated inside rule points at
`/components/<n>/inside` rather than at a `rules` array it is not in. Reason: the inside's verdict
was recorded and then silently lost, in two independent places.
`requires_violations` wrote `rule_ids: ["STORE-REQUIRES-COMPLETE"]` while the observation carried no
record under that id, so `trace_valid_violations` dropped the violation from the report and
`validate` answered `observation.incomplete` naming an internal record id instead of the import that
crossed the boundary: an inside whose rule fires reported less than an inside with no rule at all.
[AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md) claims that verdict reaches both the view and the exit code through the records every other
verdict travels in; it did not, and `check` never saw the level at all, because
`materialize_declarations` copied the contract and its provenance documents and nothing else, so
both snapshots observed the level above while the lock had been written over both and could never
be verified again. Neither showed, because the only declared inside in existence was Archkeel's own
`check`, which satisfies its `complete_requires` and whose lock no demo rebuilds. Four cheaper ways
were rejected. Projecting the inner rules under their bare ids renames nothing, but an inner rule
named like an outer one then becomes a duplicate record id, which fails the whole observation
instead of the contract that caused it. Renaming the ids on the records and the violations after
they are built leaves the one fact in two places to be kept in step, and the violation's own
`stable_id` still collides. Splitting the parent off the rule id where a derivation
needs to know the level decides behaviour from a name, which is what `parent_id` exists to avoid.
Letting `trace_valid_violations` accept a violation whose rule is missing would silence every broken
evidence chain, which is the only thing that check is for. Limit: every inner rule is recorded,
while only `complete_requires` is evaluated inside ([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)), so a record can state a decision the
level does not yet enforce; projecting only the evaluated kind would hide the others from the reader
as well as from the gate. An inside contract's own provenance documents are still not carried, for
the same reason no command reads them. Check: the shop sample declares an inside for `store` whose
four sub-components cross at three edges, the catalogued `class-a-complete-requires-inside` row
drops one `requires` entry and reads three `rule.violated` findings under
`store:STORE-REQUIRES-COMPLETE` at `/components/1/inside`, `class-a-decision-open` still reports
its open pair with an inside declared, and every `check` protocol row verifies its lock over both
levels.

