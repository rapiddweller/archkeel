# AD-50 An edge and an interface record who decided them, and the agent-decision count counts them

A `requires` entry gains an optional `decided_by`, and a component gains one that covers
its `public` list and defaults every `requires` entry that names nobody of its own.
`agent_decisions` stops counting rules alone: one decision is now one rule declaration, one
`requires` entry or one declared `public` list, at either level ([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)), and the pair stays
`[agent, total]` so an existing consumer reads the same shape. A declaration nobody attributed
counts in the total alone, because the decision was still made; a component that declares no
`public` recorded no interface decision and adds nothing. The projected component record carries
`requires` as `{component, decided_by}` entries with the default already resolved, and its own
`decided_by`, so the count comes from `architecture.json` bytes alone like every other ([AD-16](ad-16-onboarding-defines-a-target-architecture-in-two-agent-modes.md)),
and the top-level record shows the declared edges it never carried before. `init` marks each
`public` list it drafts `decided_by: "agent"`, the way it already marks the rules it drafts.
`ANALYZER_VERSION` rises to 0.23.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)). Archkeel's own three contracts record
`decided_by: "architect"` on all twelve components, which covers eight top-level `requires`
entries, six inside ones and eleven `public` lists: every rule in them was already
`architect`-decided in the same commits, and the AD log carries each edge and facade ([AD-4](ad-04-module-length-alone-does-not-justify-a-split.md) for
`analyzer` → `ir`, [AD-9](ad-09-components-declare-their-interface.md) for `public`, [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) and [AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md) for the insides), so `validate` now reports
`agent_decisions [0, 41]` where it reported `[0, 16]` rules. Reason: in a target-first contract
most decisions are exactly these edges and interface entries — which direction is allowed, which
name is the facade — so the audit question "who decided this, and was it reviewed" could not be
answered for them, and an auto-mode agent could draft a whole `public` surface that no count ever
mentioned. Rejected: turning `public` entries into objects, which would break every existing
contract for a field most contracts write per module. A second component field such as
`public_decided_by` beside a `requires`-only default, because two fields would hold one idea and
an architect would have to write both for the common case where one person decided the whole
boundary. A per-entry `provenance`, because a component already carries a required `provenance`
list pointing at the document that holds its reasons, and a second pointer to the same document
is a second source of one fact. A separate `entry_decisions` counter beside `agent_decisions`,
because a reviewer would have to add the two up to learn what is owed, and the terminal line
would print either one number that understates or two that compete. Leaving unattributed entries
out of the total, because the denominator would then describe only the contracts that adopted
this field. Limit: an attribution is one field per component, so a `public` list decided by two
people records the one the architect writes, and only a `requires` entry can disagree with it; a
count is not a finding, so the reviewer still reads the contract to see which edge is which, the
way `decided_by` on rules already works; and nothing checks that a stated decider is true. Check:
`tests/test_decisions.py::test_agent_decisions_counts_requires_entries_and_public_lists`,
`tests/test_analyzer.py::test_component_projection_writes_who_decided_each_edge_and_the_public_list`,
`tests/test_decisions.py::test_agent_decisions_counts_one_flipped_rule_from_the_observation`
counting 46 where it counted 35,
`tests/test_onboarding.py::test_deciding_every_open_pair_from_init_options_makes_validate_pass`
reading init's drafted lists, and `tests/contracts/valid/decided-by-entries.json` with
`tests/contracts/invalid/requires-decided-by-unknown.json` in `tests/test_contract_model.py`'s
corpus and round-trip tests.
