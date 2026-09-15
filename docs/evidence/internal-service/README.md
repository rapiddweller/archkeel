# Onboarding an internal 13-component service

Release gate for 0.3.0: an agent onboarded a real internal Python service with the release-candidate
wheel, following [docs/onboarding.md](../../onboarding.md), until `archkeel validate` exited 0. This
page records the artifacts and what the run showed, including what did not work.

The service is private. Every artifact here is an anonymized derivation: components are `c01`–`c13`,
internal module and symbol names are replaced by neutral tokens (`n0042`, `T0181`), evidence source
lines are removed, rationales are rewritten without business terms, and source, contract and commit
digests are zeroed. Structure, counts, rule kinds and verdicts are unchanged. Before commit, a leak
check compared every published file with the words of the private source and with every
source-shaped string in its observation. It found no private identifier and no source line; the only
matches were generic architecture words such as `worker`, `routers` and `pipeline`, which were
reviewed by hand. The digests cannot be reproduced from this page.

## Artifacts

| File | What it shows |
|---|---|
| [architecture-contract.json](architecture-contract.json) | The onboarded contract: 13 components, 11 with `public` interfaces, 122 rules |
| [architecture.md](architecture.md) | Component roles and the observed import graph with 37 component edges |
| [report-onboarded.html](report-onboarded.html) ([preview](report-onboarded.png)) | `report` on the onboarded contract: PASS, no violations |
| [proposed-rules.json](proposed-rules.json) | Two `forbidden_construct` rules proposed from observed constructs, not yet accepted by the owner |
| [report-proposed-rules.html](report-proposed-rules.html) ([preview](report-proposed-rules.png)) | `report` with the proposed rules: FAIL, 17 violations |
| [documented-intent-rules.json](documented-intent-rules.json) | Seven `forbidden_dependency` rules taken from the service's own architecture document |
| [report-documented-intent.html](report-documented-intent.html) ([preview](report-documented-intent.png)) | `report` with the documented intent: FAIL, 200 violating import sites on 7 component edges |

All reports were rendered with Archkeel at `c46ba7c`, after the report headline fix (AD-14). The
onboarding itself ran with the release-candidate wheel built at `2d825f9`.

## The run in numbers

| Step | Result | Time |
|---|---|---|
| Snapshot | Committed state only, extracted with `git archive`; 67 files, 4,318 calls | — |
| `skill install claude` | Exit 0 | 0.47 s |
| `init` under the default Python 3.11 | Exit 2: coverage FAIL, 4 `SyntaxError` records, one `runtime_mismatch` cause repeated 4 times | 0.97 s |
| `init --python 3.12` | Exit 0: 13 components, 119 forbidden pairs, closed world, no cycles | 1.13 s |
| `validate` before rationales | Exit 2: 122 `TODO` rationale diagnostics | ~1.0 s |
| `validate` after drafted rationales | Exit 0 | 1.05–1.40 s |
| `report`, repeated and with `PYTHONHASHSEED`, `TZ` and `LC_ALL` varied | Byte-identical `architecture.json` and HTML | 1.5–1.75 s |

The agent drafted all 122 rationales and rated them 93 high, 28 medium and 1 low confidence. Human
review of those drafts is still open.

## What worked

- `init` produced a closed, acyclic contract on the first run with a matching Python. No module was
  unassigned and no `complete_assignment`, `no_component_cycles` or closed-world diagnostic remained.
- The `public` drafts were right-sized in most components: where a module exports many names but one
  crosses a boundary, `init` declared that one symbol instead of the whole module.
- `validate` turned onboarding into a finite list: 122 diagnostics, each with a JSON Pointer.
- Determinism held on real code, including the environment-varied repeat.
- Every command finished in under two seconds on 67 files.

## What did not work

1. **A clean first report is a tautology.** `init` writes the forbidden pairs as the complement of the
   observed import graph, so `validate` and `report` on the same snapshot cannot find a violation.
   Exit 0 proves the contract matches the code, not that the architecture is good. The first real
   test of these 119 rules is the next change.
2. **The contract encodes the code, not the documented intent.** The service's own architecture
   document says the application layer knows only the domain and the ports. The code also imports the
   persistence adapter and both compute adapters, which a later design decision explains. The agent
   found this by reading prose; Archkeel only froze the observed edges. Written as seven
   `forbidden_dependency` rules, that document's dependency list makes the first run fail: 7 observed
   edges are forbidden (`closed_world.observed_forbidden`) and 200 import sites violate them. The
   checker was never the gap; the rules only carry intent when someone other than `init` writes them.
3. **119 pair rationales carry 14 ideas.** The drafts are one statement about the source component
   plus "so it must not depend on `<target>`". `validate` rejects repeated rationales, but the target
   suffix makes every text distinct. The format forces repetition, and the check measures form, not
   truth.
4. **Constructs are observed but not onboarded.** The scan recorded 17 `assert` statements (16 in the
   HTTP edge, used for `Optional` narrowing that disappears under `python -O`) and 6 broad `except`
   blocks. `init` drafts no `forbidden_construct` rule, so the onboarded contract is silent about them.
   The proposed rules make them visible: 17 violations, with the 6 broad `except` blocks allowed at
   four pipeline and service boundaries.
5. **The first command fails in a misleading way.** Under a Python older than `requires-python`, `init`
   reports four `SyntaxError` records and a coverage FAIL before the one diagnostic that names the
   cause. That diagnostic is repeated once per failed file.
6. **The installed skill skips interface review.** `SKILL.md` never asks the agent to review the
   drafted `public` lists; only `docs/onboarding.md` does, and the skill does not link it.
7. **Some generated text is unchecked.** The responsibility column in `architecture.md` stayed `TODO`
   while `validate` exited 0.
8. **`report` writes into the repository by default.** `test-artifacts/architecture/` is not in a
   typical `.gitignore`.
9. **One interface concern was not confirmed.** The agent flagged a package-level `public` entry that
   declares 17 names while 2 cross the boundary. Removing the entry produced neither a violation nor a
   diagnostic, so either the imports resolve to other declared names or the check cannot see this
   case. It is unresolved.
10. **Component rules are coarse.** One port-to-kernel edge carries only an identifier type and a value
    type; a component rule cannot tell that apart from infrastructure use.
11. **Calls are only partly resolved.** 998 of 4,318 calls (23.1%) are unresolved and 380 partially
    resolved. The import graph is complete; the call-level picture is not.

## What is checked deterministically

| Topic | How it is decided | Deterministic |
|---|---|---|
| Forbidden component pairs, cycles, complete assignment, closed world | AST facts compared with the contract | Yes; bytes measured identical |
| Imports resolve to declared `public` names | AST facts compared with `public` | Yes |
| `assert` and broad `except` | Counted as facts; enforced only with a `forbidden_construct` rule | Counts yes, gate only when declared |
| Graph in `architecture.md` matches observed edges | `graph.drift` diagnostic | Yes |
| Rationale present, not `TODO`, not repeated | Validation diagnostics | Form yes, truth no |
| Rationale is true | Owner review | No |
| Responsibility column filled | Not checked | No |
| Code matches the documented intent | Not checked; found by reading prose | No |
| An observed edge is intended | Owner review; `init` accepts every observed edge | No |
| Python version matches the project | `runtime_mismatch` diagnostic | Yes, but surfaced after parse errors |
| Regression between commits | `check` with an accepted baseline; not exercised in this run | Yes, when run |

## Candidates for rules and fixes

- Draft `forbidden_construct` rules with `TODO` rationales from observed constructs.
- Report a `TODO` responsibility cell as a validation diagnostic.
- Check `requires-python` before scanning and report the mismatch once.
- Allow one rationale for all pairs a source component must not depend on.
- Generate the onboarding steps in `SKILL.md` from `docs/onboarding.md`.
- Run a leak check on every evidence document derived from private code.
