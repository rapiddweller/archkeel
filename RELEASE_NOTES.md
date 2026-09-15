# Archkeel 0.3.0 — The architect owns the target

Archkeel 0.3.0 turns onboarding into decisions about a target architecture. `init` proposes
components and interfaces but never decides a dependency; the architect decides every component
pair, directly or by reviewing what an agent decided, and the report draws where the code departs
from that target.

## Highlights

- **Component flow in the HTML report.** Component cards, edges weighted by import sites, violated
  edges with the rule they break, undecided edges in their own state, a legend and the heaviest
  connections. Offline, no external library, derived from `architecture.json` alone.
- **Onboarding as a decision interview.** Every ordered component pair must be decided once, by an
  `allowed_dependency` or a `forbidden_dependency` rule with a rationale. `init --json` and
  `validate --json` list the open decisions heaviest first, each with the exact rule to choose.
- **Two agent modes.** The packaged skill runs an interview (read ADRs and documents, recommend,
  ask only about conflicts and gaps, ask why on a deviation) or auto mode (the agent decides from
  documents, then principles, then labeled judgment). Every rule records `decided_by`, and reports
  count the agent decisions the architect has not reviewed.
- **Decided means enforced, and counted once.** A `forbidden_dependency` between two components
  applies to every package of both, and an import it rejects is not counted again as an interface
  violation (AD-18).
- **Measured on a real service.** A 13-component internal service was onboarded by interview and,
  blind, in auto mode: 156 pair decisions each, first reports FAIL with 162 and 199 violations, and
  the agent matched 140 of the architect's 156 decisions before review. Anonymized evidence and the
  findings that did not work are in `docs/evidence/internal-service/`.

## Breaking changes

- **Contract 2.1.0.** Adds `allowed_dependency` and a required `decided_by` on every rule. A 2.0.0
  contract no longer decodes; decide each component pair and set `decided_by`.
- **Validation codes.** `decision.open` replaces `closed_world.missing`; `decision.conflict` is new.
  An observed import no longer counts as a decision.
- **`init` output.** `init` writes no dependency rule and returns `open_decisions`.
- **`accept` removed.** The placeholder command, which always exited 2, is gone until acceptance is
  implemented.
- **Analyzer version 0.10.0.** Observations from earlier analyzers are not comparable.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

# Archkeel 0.2.0 — Deterministic onboarding

Archkeel 0.2.0 lets a coding agent set up the architecture contract and keeps every decision
it cannot make visible as a validation diagnostic.

## Highlights

- `archkeel init` observes the only top-level package and drafts `archkeel.toml`, a closed
  Contract 2.0 and `docs/architecture/architecture.md`. On Archkeel itself it reproduces the
  hand-written component rules pair for pair.
- `archkeel validate` checks contract structure, package and provenance references, closed-world
  coverage, rule rationales and the marked component graph. Every diagnostic names a JSON
  Pointer, so the output is the onboarding worklist.
- `archkeel skill install claude|codex` installs one packaged instruction source for coding
  agents; [docs/onboarding.md](https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md)
  contains the prompt to hand over.
- The class-A rule catalog is enforced: `forbidden_dependency`, `forbidden_construct`,
  `external_dependency_scope`, `complete_assignment` and `no_component_cycles`, each proven by
  a violation test. See [docs/rules.md](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md).
- Terminals get a Rich summary with the decision sentence of the HTML report, verdicts,
  regression checks and diagnostics. Every command has `--help` with examples and exit codes,
  and `--json`.
- `schema/architecture-contract.schema.json` describes Contract 2.0; tests keep it equal to the
  parser verdict on a valid and invalid corpus.

## Breaking changes

- **Contract 2.0.0.** Class-C fields move under `declarations`. A 1.1.0 contract returns exit
  `2` with a migration remedy; follow
  [Migrating from 1.1.0](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md#migrating-from-1-1-0).
- **Terminal output.** When stdout is a terminal, `report`, `check` and `validate` print the
  summary. Pipes still receive JSON; pass `--json` to get JSON in a terminal.
- **Dependencies.** `rich` and `rich-argparse` are new runtime dependencies. Contract rules
  confine them to `archkeel.render.terminal` and `archkeel.cli`.
- **Diagnostics.** The new kind `existing_files` reports that `init` would overwrite files.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel's analyzer measured its own source at `0ffd413` and at this release:

| Measurement | 0ffd413 | 0.2.0 | Explanation |
|---|---:|---:|---|
| Source files | 38 | 43 | Onboarding, terminal view, skill, summary and rule evaluation modules |
| Violations | 0 | 0 | Now including construct, dependency-scope, assignment and cycle rules |
| `getattr` calls | 14 | 0 | Replaced by explicit types |
| Typing positions | 180 | 187 | +14 raw record annotations in the new rule evaluation module |
| Unresolved calls | 507 / 2547 | 593 / 2830 | New calls into Rich, argparse and standard-library values |

The unresolved ratio rose from 19.91% to 20.95% only in new modules; existing modules such as
the scanner, report and validation resolve more calls than before.

# Archkeel 0.1.0

Archkeel adds deterministic architecture evidence to AI-assisted code review.
It checks whether a repository remains observable, follows its architecture
contract, and matches a change declaration published before submission.

## Highlights

- Run as a standalone Python package with the bundled analyzer.
- Define scan roots, namespace, and contract in `archkeel.toml`.
- Generate canonical `architecture.json` evidence with `archkeel report`.
- Review the same evidence in a self-contained `interactive.html` report.
- Compare accepted and candidate commits with `archkeel check`.
- Detect forbidden imports, cycles, private crossings, typing regressions,
  unresolved-call regressions, coverage loss, and changed finding fingerprints.
- Keep scan completeness, contract compliance, and expectation fulfillment as
  three separate verdicts.
- Return stable exit codes: `0` for pass, `1` for rejection, and `2` when the
  result cannot be verified.
- Validate declaration order from supplied host records or GitLab merge-request
  evidence.

## Install

Archkeel requires Python 3.11 or newer.

```bash
python -m pip install archkeel==0.1.0
archkeel --help
```

## Quick start

Add `archkeel.toml` to the repository:

```toml
[scan]
roots = ["src/example"]
namespace = "example"
contract = "architecture-contract.json"
```

Generate architecture evidence:

```bash
archkeel report --root . --output architecture.json
```

The command writes `architecture.json` and a portable `interactive.html` review
surface beside it.

## Current scope

- Python repositories are supported.
- `report` and `check` are available.
- `accept` is a placeholder and returns exit `2`.
- GitHub is used for distribution and CI; declaration-order retrieval currently
  has a GitLab adapter. Portable host records can be supplied explicitly.

See the [README](https://github.com/rapiddweller/archkeel) for the full protocol,
configuration, check command, and report preview.
