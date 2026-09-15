# Onboarding an internal 13-component service

Release gate for 0.3.0. The service's owner acted as architect. On one committed snapshot, Archkeel
was onboarded twice:

1. **Interview mode.** An agent asked and the architect decided.
2. **Blind auto mode.** A second agent decided every dependency without seeing the architect's
   answers.

This page records both targets, what the first reports measured, how far the agent's decisions
matched the architect's, and what did not work.

The service is private, so every artifact here is anonymized:

- Components are `c01`–`c13`, and internal module and symbol names are neutral tokens (`n0042`,
  `T0181`).
- Evidence source lines are removed.
- Rationales are replaced by neutral text that keeps who decided and on what basis.
- Source, contract and commit digests are zeroed.

Structure, counts, rule kinds, `decided_by` and verdicts are unchanged. Before commit, a leak check
compared every published file with the words of the private snapshot and with every source-shaped
string of its observation: it found none. The only hand-reviewed matches were generic English words
in the neutral texts.

## Artifacts

| File | What it shows |
|---|---|
| [architecture-contract-interview.json](architecture-contract-interview.json) | The architect's target: 13 components, 156 pair decisions and 3 structural rules, all `decided_by: architect` |
| [report-interview.html](report-interview.html) ([flow](report-interview-flow.png)) | `report` on that target: FAIL, 162 violations |
| [architecture-contract-auto.json](architecture-contract-auto.json) | The blind auto-mode target: the same components and structural rules, 156 pair decisions `decided_by: agent` |
| [report-auto.html](report-auto.html) ([flow](report-auto-flow.png)) | `report` on that target: FAIL, 199 violations, "156 of 159 rules decided by the agent" |
| [decisions-interview-vs-auto.json](decisions-interview-vs-auto.json) | Every pair with the architect's blind decision, the architect's final decision, and the agent's decision with its basis and confidence |

All reports were rendered with Archkeel at `8531bdb` under Python 3.12.

## The target

The architect accepted the proposed components as a base and changed three things before any
dependency was decided:

- split the shared kernel by layer into `c06`, `c07` and `c08`;
- merged a pipeline executor into the worker (`c12`);
- joined the entry module and the settings module into one composition root (`c01`).

After that, the architect reviewed the drafted `public` lists:

- narrowed the persistence adapter (`c09`) to its repositories;
- narrowed the use cases (`c03`) to the twelve classes other components import;
- kept heartbeat constants private on purpose, so their use shows as violations.

| | Interview | Blind auto mode |
|---|---:|---:|
| Pair decisions | 156 by the architect | 156 by the agent |
| Allowed / forbidden | 43 / 113 | 39 / 117 |
| Violations in the first report | 162 | 199 |
| `DEP-C03-NO-C09` (use cases import the persistence adapter) | 148 | 148 |
| `INTERFACE-BOUNDARY` | 4 | 6 |

Both targets forbid the heaviest observed edge, from use cases to the persistence adapter, at 148
import sites. Each rejected import counts once (AD-18): before that decision the interview report
showed 307 violations, because 145 of its 149 interface violations were the same imports a forbidden
dependency already rejected.

## Agreement

The agent's decisions were scored before the architect saw any of them.

| Pairs | Agreement |
|---|---:|
| All | 140 / 156 = 89.7% |
| Observed in the code | 29 / 39 = 74.4% |
| Not observed | 111 / 117 = 94.9% |

The agent based 62 decisions on an explicit document statement, 60 on a documented layer principle
and 34 on its own judgment. Ten of the 16 mismatches were decisions the agent had based on a
document statement.

The architect then reviewed the 16 mismatches and changed 8 decisions toward the agent:

- Three came from bulk answers that accidentally contradicted an explicit statement in the service's
  architecture document.
- Five changed after the agent asked why the architect had chosen against the recommendation.

The remaining 8 mismatches are deliberate choices by the architect, for example allowing the
composition root to reach every component. The post-review figure of 148 of 156 is not an
agreement rate, because the reference moved after scoring.

## What worked

- The first report of a decided target fails where the intent says it should. The earlier
  onboarding model wrote the complement of the observed graph and could only pass.
- Reading the documents first gave the agent a basis it could cite. Its high-confidence decisions
  were its document-based ones.
- Asking why on a deviation changed five decisions, among them the heaviest disputed edge at 43
  import sites, without any code change.
- `decided_by` kept agent decisions countable after the fact.
- The flow view made the one edge that matters, `c03 → c09`, the widest line on the page.

## What did not work

1. **The first interview overwhelmed the architect.** It asked about 20 rounds of unranked
   questions over 156 pairs. This led to AD-16: recommendations with evidence, the overall picture
   confirmed once, and questions only about conflicts and gaps.
2. **Bulk answers hid contradictions.** Three pair decisions answered "for the whole group"
   contradicted the documents. Only the blind comparison surfaced them.
3. **Five product defects appeared only on this real run.** All are fixed in 0.3.0:
   - Open decisions showed edges into components with several packages as unobserved: 62 of 620
     import sites. The architect could have forbidden, in bulk, an edge the code uses.
   - The interview's stop condition was "`validate` exits 0". A forbidden observed edge keeps
     `validate` at exit 2 correctly, so the loop could never end. It now ends when no
     `decision.*`, placeholder or duplicate diagnostic remains.
   - A `forbidden_dependency` between two components enforced only the first package of a
     multi-package component, so 2 import sites were missed.
   - The agent-decision count re-read the contract, so a report rendered from `architecture.json`
     alone could not show it.
   - An import that a forbidden dependency rejected also counted as an interface violation, which
     nearly doubled the first report's headline.
4. **Delegated answers were worded by the agent.** Twice the architect answered "whatever is
   consistent". The six decisions derived from the architect's earlier answers were confirmed later,
   but their wording is the agent's.
5. **The toolchain must match the target.** One evidence build ran under Python 3.11 against a
   3.12 service and produced `runtime_mismatch` instead of a report.

## Not fixed in 0.3.0

- A package's `__init__` module cannot be assigned without owning its subpackages, so
  `complete_assignment` reports one violation after the shared kernel split.
- After a component cut, the marked graph in `docs/architecture/architecture.md` drifts, and no
  command regenerates it.
- `package_dependency` records cut module names to two dotted segments (see
  [known limits](../../known-limits.md)).
- The agreement rate is one service measured once. It is not a general accuracy of auto mode.

## What is checked deterministically

| Topic | How it is decided | Deterministic |
|---|---|---|
| Every component pair decided exactly once | `decision.open`, `decision.conflict`, `closed_world.duplicate` | Yes |
| Forbidden pairs, including components with several packages | Rule violations from the observation | Yes |
| Imports reach declared `public` names | `interface_boundary` | Yes |
| How many rules the agent decided | `decided_by` count in `validate` and `report` | Yes; whether the architect has read them, no |
| Rationale present and not a placeholder | Validation diagnostics | Form yes, truth no |
| Quality goals behind a decision | Text in the rationale | No |
| Agreement between two targets | Pair-by-pair comparison of two contracts | Yes for given contracts; the agent's decisions themselves are not reproducible |
| Code matches documented intent | Only once the intent is decided as rules | Yes after deciding, no before |
