# Onboarding an internal 13-component service

Release gate for 0.3.0. The service's owner acted as architect. On one committed snapshot, Archkeel
was onboarded twice:

1. **Interview mode.** An agent asked and the architect decided.
2. **Blind auto mode.** A second agent decided every dependency without seeing the architect's
   answers.

The service is private, so every artifact here is anonymized:

- Components are `c01`–`c13`, and internal module and symbol names are neutral tokens (`n0042`,
  `T0181`).
- Evidence source lines are removed.
- Rationales are replaced by neutral text that keeps who decided and on what basis.
- Source, contract and commit digests are zeroed.

Structure, counts, rule kinds, `decided_by` and verdicts are unchanged. A pre-commit
leak check found no private snapshot words or source-shaped strings. Hand-reviewed
matches were generic English in neutral text.

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

Both targets forbid the heaviest edge, use cases → persistence, at 148 import sites.
Before AD-18 counted each rejected import once, the interview report showed 307
violations: 145 of 149 interface findings duplicated forbidden-dependency findings.

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

The remaining 8 mismatches are deliberate architect choices, such as allowing the
composition root to reach every component. The revised 148/156 is not an agreement
rate: the reference changed after scoring.

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

1. The interview asked about 20 unranked rounds over 156 pairs. AD-16 replaced
   this with one overall confirmation and questions about conflicts/gaps.
2. Bulk answers contradicted three documented pair decisions. Only the blind
   comparison surfaced them.
3. Five defects appeared on this run, all fixed in 0.3.0:
   - Open decisions mislabeled 62 of 620 imports into multi-package components as unobserved.
   - The interview waited for exit 0, which forbidden observed edges correctly prevent.
     It now waits for no `decision.*`, placeholder or duplicate diagnostic.
   - Forbidden dependencies checked only the first owned package, missing 2 sites.
   - Agent-decision counts re-read the contract instead of surviving in saved observations.
   - Interface findings duplicated rejected dependency imports.
4. Six delegated decisions were worded by the agent from earlier architect answers.
   The architect later confirmed them.
5. Python 3.11 against the 3.12 service returned `runtime_mismatch`; match the toolchain.

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
