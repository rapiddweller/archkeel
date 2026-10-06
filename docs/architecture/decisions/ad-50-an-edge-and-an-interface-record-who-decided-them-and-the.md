# AD-50 An edge and an interface record who decided them, and the agent-decision count counts them

A component's optional `decided_by` attributes its `public` list and defaults
its requirements; each requirement can override it. `agent_decisions` counts
rule declarations, requirements and declared public lists at both levels
([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)), retaining
`[agent, total]`. Unattributed declarations count only in total; absent public
lists add nothing.

Component records resolve defaults and carry requirement and interface attribution,
so counts derive from observation bytes ([AD-16](ad-16-onboarding-defines-a-target-architecture-in-two-agent-modes.md)).
`init` marks drafted public lists as agent decisions. Analyzer version rises to
0.23.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).

The self-contracts marked twelve components architect-decided, covering eight
outer and six inside requirements and eleven public lists. Existing rule and ADR
ownership ([AD-4](ad-04-module-length-alone-does-not-justify-a-split.md),
[AD-9](ad-09-components-declare-their-interface.md),
[AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)) supported this;
validation changed from `[0, 16]` to `[0, 41]`.

Rule-only counts had hidden auto-drafted boundaries awaiting review. Component
attribution avoids breaking public strings or duplicating provenance and counters.
Limits: one attribution covers a mixed-authorship public list; only requirements
override it. Counts identify no particular edge and do not prove attribution true.

Checks: decision counts, projection defaults, init lists and contract corpus/round
trips in `test_decisions.py`, `test_analyzer.py`, `test_onboarding.py` and
`test_contract_model.py`; the flipped-rule fixture count changed from 35 to 46.
