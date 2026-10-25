# Get started with ArchKeel

This guide takes you from a repository with no contract to a first overview.
It takes about 15 minutes. The commands run in your repository root.

The examples below are real output from a copy of the public fastmcp
repository, made with this version of ArchKeel. The copy was not changed
except for removing ArchKeel's own files. They are examples, not a
recommendation for fastmcp.

## 1. Install

```bash
uv tool install archkeel
archkeel skill install claude    # or: archkeel skill install codex
```

Requires Python 3.11+ and a Git repository with at least one commit.
The skill gives your coding agent the ArchKeel instructions. Use `/archkeel`
(Claude Code) or `$archkeel` (Codex) in a new session.

## 2. Run `init`

```bash
archkeel init
```

`init` reads your source files and writes three files:

- `archkeel.toml`: where ArchKeel reads your code.
- `architecture-contract.json`: the components and rules it proposes.
- `docs/architecture/architecture.md`: a page to edit.

`init` is a draft. It gives no permission for any dependency. An existing
import is evidence that the code uses it, not approval. This example ends
with the first overview lines and the next steps:

```text
Example output (fastmcp, copy):
 i DRAFT  Draft written. Run archkeel validate to list every decision left.

 First look:
   Files parsed: 129 of 129
   Calls resolved: 62.48 %
   Module cycles: 2 (largest: 63 modules)
   Most imported module: fastmcp.utilities.logging (64 modules import it)
   Largest component: server (41 modules)
   Positions left UNKNOWN: 1

 Next steps:
   1. archkeel report            # read the overview and the first findings
   2. open test-artifacts/architecture/architecture.report.html   # the Explorer; ...
   3. archkeel init --force --adopt   # or write the target yourself (see ...)
```

## 3. Read the overview

```bash
archkeel report
```

`report` writes `test-artifacts/architecture/architecture.report.html`.
Open it in a browser. Add `test-artifacts/` to `.gitignore`, or pass
`--output` to choose another place.

The **First look** lines are facts from the first scan. They are not
grades, and no line says good or bad.

| Line | What it means |
| --- | --- |
| `Files parsed: 129 of 129` | Source files read and parsed. Equal numbers mean every file was read. |
| `Calls resolved: 62.48 %` | Share of call sites whose target ArchKeel could name. A low share means less of the call graph is known. |
| `Module cycles: 2 (largest: 63 modules)` | Groups of modules that import each other in a loop. Two groups; the largest has 63 modules. `none` means no loop. |
| `Most imported module: ...` | The module that the most other modules import. |
| `Largest component: server (41 modules)` | The drafted component with the most modules. A tie lists every tied component. |
| `Positions left UNKNOWN: 1` | Places ArchKeel could not decide. |

The Explorer shows the components as a dependency diagram. Click a
component name to select it; the selection details show what it holds.
The **As-Is** view shows the code as observed. The **Target** view shows
the architecture you declare. The **Diff** view shows the difference.

## 4. Read the first verdict

```bash
archkeel validate
```

On a new draft the verdict is FAIL. Example output (fastmcp, copy):

```text
Example output (fastmcp, copy):
 × FAIL  The scan completed; validation diagnostics rejected the contract.
 FAIL rules: ASSIGNMENT-COMPLETE, INTERFACE-BOUNDARY.
 132 open decision(s) remain.
 12 of 12 decisions made by the agent, awaiting the architect.
```

A FAIL on a draft comes from the draft, not from a verdict on the code.
The draft has three kinds of gaps:

- **Open decisions.** 132 ordered pairs of components have no decision.
- **Placeholder reasons.** The draft's rules say `TODO`. The validator rejects them.
- **Rules the agent wrote.** The draft's rules and interface lists are guesses from the code.

The line **12 of 12 decisions made by the agent, awaiting the architect**
means this: the agent wrote all 12 decisions in the draft. A person has
not yet read or confirmed any of them. Each one is marked `decided_by:
"agent"` until an architect changes it.

Exit codes for `validate`:

- `0`: the check ran, and no violation is new (with a baseline).
- `1`: a violation is new, measured against the baseline.
- `2`: the contract was rejected, or the check could not run. Read the diagnostics.

## 5. Choose how to start

You have two ways forward. Pick one. Path A replaces the draft files with `--force`,
so commit your work first.

### A. Take today's state: `archkeel init --force --adopt`

```bash
archkeel init --force --adopt
archkeel validate --baseline architecture-baseline.json
```

`--adopt` does three things:

- It records every observed crossing between two components as a
  `requires` entry. Each entry says `decided_by: "agent"` and the reason
  "Observed when the contract was drafted; not reviewed."
- It forbids every other component pair, with one `complete_requires` rule.
- It writes `architecture-baseline.json` with today's violations.

After this, `validate --baseline` exits `0` on the same code. A new
crossing between components that already talk exits `1`. A new name imported
from another component also exits `1`.

Use this path to stop new drift now, and review the recorded decisions later.
It does not say that today's crossings are correct.

One case needs one more step. A crossing from a component to a component it
did not use before changes the drawn graph. Then `validate` exits `2` with
`graph.drift`. Run `archkeel validate --write-graph`, review the change to
`docs/architecture/architecture.md`, and run `validate` again. It then exits `1`
if the crossing breaks a rule.

### B. Write the target yourself

Open the Explorer's **Target** view and decide what each component may use.
Then edit the contract, or ask your coding agent to do it with the skill
(`/archkeel` or `$archkeel`). The architect decides each dependency. The
agent proposes. Replace every `TODO` reason with your own words, then run
`archkeel validate`.

## 6. Keep it green in CI

Commit `archkeel.toml`, `architecture-contract.json`,
`architecture-baseline.json` and `docs/architecture/architecture.md`. The contract names
that page as the source of its reasons, and `validate` exits `2` when it is missing in a
fresh checkout. Then run this in CI:

```bash
archkeel validate --baseline architecture-baseline.json
```

- Known violations stay in the baseline. They show as FAIL in the report, but they do not fail the build.
- A new violation fails the build with exit `1`.
- A contract that is rejected fails with exit `2`. Read the diagnostics.

When you fix a known violation, update the baseline in the same change:

```bash
archkeel validate --baseline architecture-baseline.json --write-baseline
```

Review the file diff before you commit it.

## Where to go next

- [Onboarding](onboarding.md): the full setup, the `requires` format and the target loop.
- [Reference](reference.md): the commands, flags and exit codes.
