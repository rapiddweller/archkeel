# Archkeel

**Architecture checks for coding agents.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-5EEAD4?labelColor=141414)
[![CI](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml/badge.svg)](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/archkeel)](https://pypi.org/project/archkeel/)
[![MIT](https://img.shields.io/badge/license-MIT-C5F82A?labelColor=141414)](https://github.com/rapiddweller/archkeel/blob/main/LICENSE)

Archkeel checks code against your architecture rules. It shows forbidden imports,
misplaced types, and gaps in the analysis, with source evidence you can review.
It runs locally and in CI. The checks are deterministic; they do not call an LLM.

In a coding-agent harness, Archkeel supplies architecture feedback before submission.
Tests check behavior. Archkeel checks declared boundaries and whether a change made
static analysis less complete. Both still need human review.

## Start here

Requires Python 3.11+ and a Git repository with at least one commit.
Run Archkeel with a Python version that meets your project's requirements.

```bash
uv tool install archkeel
archkeel skill install codex    # or claude
```

Then ask your coding agent:

```text
Set up Archkeel for this repository. Read the architecture documents,
propose the boundaries, and let me decide which dependencies are allowed.
```

The skill guides the setup. `init` drafts components and interfaces;
you decide the target architecture. Existing imports are evidence, not permission.
You can delegate decisions to the agent, but its authorship is recorded separately.
See the [onboarding guide](docs/onboarding.md) for setup and plugin installation.

For an existing setup:

```bash
archkeel report      # inspect code and evidence
archkeel validate    # check the contract
```

`report` writes `architecture.json` and an offline `architecture.report.html`.
Read the verdicts: a report can exit `0` with failed or undecided rules.
`validate` checks the contract; `check` also compares a submitted change with its
published expectation. Use `archkeel <command> --help` for command options.

## Review the evidence

<p>
  <img src="docs/assets/archkeel-report-preview.png" alt="Shop report with scan status, failed rules and separate verdicts" width="1000">
</p>

Use the report to inspect findings and source locations, then explore the components.
Filters narrow the view without changing the verdicts.

```bash
archkeel report --only violations --component store
archkeel report --only calls --component store
```

The explorer shows **Actual** (observed code), **Target** (declared architecture),
and **Diff** (their differences). These are views of one snapshot, not two revisions.
Folders help navigation; they do not establish ownership or runtime behavior.

`PASS` means the required rules have complete evidence and no decided violation.
`UNKNOWN` means evidence is missing. A rule can fail and still have undecided positions.
A clean graph does not prove a good design.

## Catch changes that finding diffs miss

This change adds no forbidden import or cycle, but makes a call harder to resolve:

```diff
 def run(key: str) -> int:
-    return first() + second()
+    handlers = {"first": first, "second": second}
+    return handlers[key]()
```

In Fixture A, resolved calls drop from 2 of 2 to 0 of 1. New finding fingerprints stay at
zero. Archkeel rejects the candidate because unresolved calls increase from 0 to 1.

`check` compares the accepted and candidate commits, checks the contract, and verifies the
candidate against an expectation published before submission. Publication order needs trusted
host records. A local replay checks supplied records without authenticating them.
The [reference](docs/reference.md) explains the commit protocol and its limits.

## Keep a target the code has not reached

Record existing violations, review the file, then reject new ones in CI:

```bash
archkeel validate --baseline known-violations.json --write-baseline
archkeel validate --baseline known-violations.json
```

Known violations remain `FAIL`. After fixing them, rewrite the baseline in the same change.
New or increased violations require explicit `--accept-new`; do not use it to hide a regression.
See the [target-first guide](docs/target-first.md) for the full workflow.

## Try a reproducible example

```bash
git clone https://github.com/rapiddweller/archkeel.git
cd archkeel
make demo
make demo-onboarding
```

`make demo` rejects a coverage regression and a late expectation, then shows a passing candidate.
`make demo-onboarding` replays setup on a two-level shop using committed decision fixtures;
it performs no live approvals. More cases are in the [demo catalog](docs/architecture-demo.md).

## Scope and limits

Archkeel observes static source in configured roots. Python support covers imports, calls, and declared boundaries;
Dart and TypeScript support imports. TypeScript roots may name files or directories. Archkeel does not prove
runtime behavior, performance, or the quality of every design decision. Separate test trees need their own
scan and contract.

| Exit | Meaning |
| ---: | --- |
| `0` | Complete report or successful check; read the individual verdicts |
| `1` | Rejected, including a baseline that needs updating |
| `2` | Input or evidence could not be verified; read the diagnostic |

Details: [rules](docs/rules.md) · [known limits](docs/known-limits.md) ·
[command reference](docs/reference.md) · [roadmap](docs/roadmap.md).

## Development

```bash
make check              # lint, types, tests
make gate               # also build, isolated installs and self-validation
make browser-install
make report-browser OUTPUT=test-artifacts/report-browser
```

Archkeel checks its own [architecture contract](https://github.com/rapiddweller/archkeel/blob/main/architecture-contract.json) and compares fresh
observations with [fixtures/D-self](https://github.com/rapiddweller/archkeel/tree/main/fixtures/D-self). See [CONTRIBUTING.md](https://github.com/rapiddweller/archkeel/blob/main/CONTRIBUTING.md).

MIT © 2026 Rapiddweller Asia Co., Ltd. Maintained by [Alexander Kell](https://github.com/ake2l).
