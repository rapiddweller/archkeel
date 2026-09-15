# Archkeel

**The agent declares before it submits. The check is deterministic.**

<p>
  <img src="docs/assets/archkeel-hero.png" alt="Archkeel architecture gate and keel" width="600">
</p>

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-5EEAD4?labelColor=141414)
[![CI](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml/badge.svg)](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-C5F82A?labelColor=141414)](https://github.com/rapiddweller/archkeel/blob/main/LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/archkeel)](https://pypi.org/project/archkeel/)

Archkeel checks architecture boundaries and declared changes in AI-assisted code.
It compares an accepted commit with a candidate, checks their scans against the
configured contract, and verifies that the candidate matches an expectation
published before its first submission.

It catches two failure modes that finding-only diffs miss:

- the architecture changed without being declared;
- the scanner saw less of the program, so the result looks clean only because
  the graph became blinder.

<p>
  <img src="docs/assets/archkeel-intent-vs-observed.png" alt="Intent versus observed for the shop sample: the contract holds on the clean sample on the left, eleven rule violations appear on the right" width="1000">
</p>

<sub>Preview of the planned component flow view (AD-10). Both panels are derived from the contract and
the scan of <code>fixtures/F-architecture</code>: lime edges match the contract, teal edges are scoped
by module rules, and red dashed edges break the named rule.</sub>

<p>
  <img src="docs/assets/archkeel-check-terminal.svg" alt="Archkeel rejects Fixture A in the terminal because calls_unresolved rose from 0 to 1" width="720">
</p>

[Try the demo](#try-the-demo) · [Onboard your project](#onboard-your-project) · [How it works](#how-it-works) ·
[Reference](https://github.com/rapiddweller/archkeel/blob/main/docs/reference.md) · [Roadmap](https://github.com/rapiddweller/archkeel/blob/main/docs/roadmap.md)

Implemented and planned work is tracked in the [roadmap](https://github.com/rapiddweller/archkeel/blob/main/docs/roadmap.md).

## Why Archkeel

An agent can keep tests green and introduce no new architecture finding while
making the code harder to analyze. If the gate compares finding identities
only, that change passes.

Fixture A is the smallest example:

```diff
 def run(key: str) -> int:
-    return first() + second()
+    handlers = {"first": first, "second": second}
+    return handlers[key]()
```

The refactor introduces no new forbidden import, cycle, or private crossing.
But static call resolution gets worse:

| Observation | Accepted | Candidate |
| --- | ---: | ---: |
| Resolved calls | 2 of 2 | 0 of 1 |
| Unresolved calls | 0 | 1 |
| New finding fingerprints | 0 | 0 |
| Archkeel verdict | baseline | **FAIL** |

```text
expectation_fulfilled: FAIL
regression check failed in calls_unresolved: 0->1
regression check failed in unresolved_ratio: 0/2->1/1
```

Archkeel compares raw measurements as well as finding counts and fingerprints.
The ratio check uses integer cross-multiplication, never rounded percentages:

```text
U_candidate × T_accepted <= U_accepted × T_candidate   (when both T > 0)
```

### What the gate adds

- **Precommitment with evidence.** The agent publishes the intended change
  before it submits the candidate. Git ancestry and host records prove the
  order; author timestamps do not.
- **Coverage-aware regression checks.** A disappearing edge is not mistaken
  for an improvement just because a finding disappeared with it.
- **Explicit uncertainty.** An incomplete scan, broken lock, empty scope, or
  runtime mismatch returns exit `2` with a diagnostic. Unknown never becomes
  green.

Archkeel complements tests, linters, and human review. It does not replace any
of them. Its job is narrower: keep architecture changes declared, observable,
and mechanically checkable.

## Review surface

<p>
  <img src="docs/assets/archkeel-report-preview.png" alt="Archkeel check report rejecting Fixture A with five independent verdicts and the failed regression checks" width="1100">
</p>

The HTML report is designed for a reviewer making a merge decision:

- **Decision first.** `PASS`, `REJECT`, or `UNVERIFIABLE` and one sentence explaining it are
  visible before details, in the HTML report and in the terminal.
- **No blended score.** Scan completeness, contract compliance, expectation matching, Git order
  and publication order remain separate verdicts.
- **Unknown stays visible.** Missing or invalid evidence includes the affected subject,
  unknown claim, and remedy.
- **Evidence stays inspectable.** Exact counts, fingerprints, source locations, digests,
  and runtime provenance remain available beside the verdict.

## Try the demo

The demo builds three small Git repositories and runs the real checks. Fixture A is rejected
because the call graph got blinder, Fixture B because its expectation was published too late,
and Fixture C passes.

```bash
git clone https://github.com/rapiddweller/archkeel.git
cd archkeel
make demo
```

`make demo-screenshots OUTPUT=<directory>` also captures each HTML report as PNG and each
terminal view as SVG.

## Onboard your project

Requirements: Python 3.11+ and a Git repository with at least one commit.

```bash
uvx archkeel skill install claude    # or codex
uvx archkeel init
uvx archkeel validate
```

The contract is your target architecture, not a copy of the code. `init` observes the only
top-level package and writes `archkeel.toml`, `architecture-contract.json` and
`docs/architecture/architecture.md`: one component per subpackage, drafted `public` interfaces and
no dependency rule. Every ordered component pair is an open decision; `init --json` and
`validate --json` list them heaviest first, each with the exact `allowed_dependency` and
`forbidden_dependency` rule to choose from. The installed skill runs onboarding in one of two
modes: an interview, where the agent reads your ADRs and documents, recommends and asks only about
conflicts and gaps, or auto mode, where the agent decides. Every rule records `decided_by`, and
reports count the decisions the architect has not reviewed yet. The prompt is in
[docs/onboarding.md](https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md); the
rule catalog is in [docs/rules.md](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md).

To install it permanently instead, run `pip install archkeel`. Every command explains itself
with `archkeel <command> --help`.

## Quickstart

Observe the current repository:

```bash
archkeel report
```

The command writes the canonical `architecture.json` and a self-contained
`architecture.report.html` beside it. A terminal shows the decision and verdicts; pipes and
`--json` receive the JSON result.

Check a candidate against its published expectation:

```bash
archkeel check \
  --root /repo \
  --baseline "$B" \
  --expectation-commit "$E" \
  --head "$H" \
  --expected expectation.json \
  --expected-digest "$DIGEST" \
  --accepted-branch main \
  --branch candidate
```

Run the Python version required by the repository being scanned. A mismatch is
reported as `runtime_mismatch` with exit `2`, not as broken source code.

## How it works

```mermaid
flowchart TB
    B["Locked accepted state"] --> O["Observe accepted + candidate"]
    E["Expectation published first"] --> H["Candidate submitted"]
    H --> O
    O --> C{"Deterministic check"}
    C --> P["0 · pass"]
    C --> R["1 · reject"]
    C --> U["2 · unverifiable"]

    classDef locked fill:#141414,stroke:#C5F82A,color:#E8E8E2
    classDef declared fill:#141414,stroke:#5EEAD4,color:#E8E8E2
    classDef candidate fill:#141414,stroke:#8A8A84,color:#E8E8E2
    classDef gate fill:#C5F82A,stroke:#C5F82A,color:#0D1F05
    classDef result fill:#141414,stroke:#2A2A28,color:#E8E8E2

    class B locked
    class E declared
    class H,O candidate
    class C gate
    class P,R,U result
```

A check answers three independent questions. It never compresses them into a
single score.

| Verdict | Question | Typical failure |
| --- | --- | --- |
| `observation_complete` | Did the scan see everything it claims to see? | Incomplete scan, empty scope, rule without subjects |
| `declared_rules` | Does the code obey the architecture contract? | Forbidden import between components |
| `expectation_fulfilled` | Did the candidate match the declaration without regressions? | Coverage regression, undeclared change, late expectation |

### Exit codes

| Exit | Meaning |
| ---: | --- |
| `0` | Complete report or successful check |
| `1` | Rejected because at least one verdict is `FAIL` |
| `2` | Unverifiable input, always with at least one diagnostic |

Every exit `2` diagnostic contains:

```text
kind · subject · unknown_claim · remedy
```

A broken lock is therefore not interpreted as an empty accepted state.

## The M → B → E → H protocol

```mermaid
gitGraph
    commit id: "M · accepted"
    commit id: "B · lock only"
    branch candidate
    commit id: "E · expectation only"
    commit id: "H · implementation"
```

| Commit | Contract |
| --- | --- |
| **M** | Accepted state. Archkeel re-observes it. |
| **B** | Lock-only child of M and tip of the accepted branch. It binds the config, checker, and observation digests. |
| **E** | Child of B that changes only the expectation file. It must be published before the first submission of H. |
| **H** | Descendant of E. It must not modify the lock, config, architecture contract, or expectation. |

### Agent workflow

1. Start from the lock commit **B**.
2. Write the intended architecture change and commit it alone as **E**.
3. Publish **E** before submitting implementation work.
4. Implement the change in one or more commits ending at **H**.
5. Run `archkeel check`. Fix the code or revise the proposal in a new protocol
   cycle; do not rewrite protected inputs inside H.

Fixture B writes its expectation after implementation by deriving it from the
observed delta. Its architecture findings are otherwise clean. Archkeel still
rejects it:

```text
host_order: FAIL
expectation_fulfilled: FAIL
expectation was not published before the first candidate submission
```

Precommitment proves "published before submission." It does not prove that no
private edit existed before publication.

## Host evidence

In GitLab CI, Archkeel reads merge-request diff versions through `glab` to
establish publication order.

For local testing, replay captured host records:

```bash
uv run archkeel check ... --host-records records.json
```

A local replay validates the record shape and behavior. It does not prove host
authenticity.

## Development

Run the complete project gate:

```bash
make check
```

This runs Ruff, strict mypy, pytest, and Archkeel's self-check.

Run the full release check, build both distributions, and install each one in isolation:

```bash
make release-check
```

Reproduce the protocol fixtures:

```bash
make fixtures
```

## Archkeel checks itself

[architecture-contract.json](https://github.com/rapiddweller/archkeel/blob/main/architecture-contract.json)
holds Archkeel to the rules it sells, and every rule was proven by a deliberate violation:

- **Every pair decided.** Six components; each of the 30 ordered pairs is an
  `allowed_dependency` or `forbidden_dependency` rule with a rationale, all decided by the
  architect. The [architecture guide](docs/architecture/archkeel.md) names the quality goal each
  allowed edge serves.
- **Deterministic core.** `ir` and `check` never import adapters or presentation; the CLI is
  the composition root. The analyzer may import only `archkeel.ir.model` and `archkeel.ir.codec`.
- **No dynamic shortcuts.** `getattr`, `hasattr`, `cast`, `eval`, `exec`, dynamic imports and
  `type: ignore` are forbidden everywhere.
- **Confined dependencies.** `packaging` only in the analyzer runtime gate, `rich` only in the
  terminal view, `rich_argparse` only in the CLI.
- **Complete and acyclic.** Every module belongs to exactly one component, and components form
  no cycle.

`make check` reobserves the repository and compares it with
[fixtures/D-self](https://github.com/rapiddweller/archkeel/blob/main/fixtures/D-self/result.json);
CI also runs `archkeel validate` and uploads the self-observation.

## Current boundaries

Archkeel is deliberately strict about what it can prove:

- **Competing implementations:** review is still required when no declared rule
  or observed regression exposes them.
- **Private crossings:** only import records are checked. `import pkg;
  pkg._member` is not detected.
- **Precommitment:** publication order is proven; private editing order is not.
- **Analyzer runtime:** Archkeel's Python must be at least the target
  repository's Python.
- **Onboarding:** `init` detects one top-level package; other layouts need `--source` and
  `--namespace`. It never decides a dependency; the architect or, in auto mode, the agent does,
  and `decided_by` keeps the difference visible.
- **Static observation:** runtime behavior, data flow and performance are not observed; see
  [docs/known-limits.md](https://github.com/rapiddweller/archkeel/blob/main/docs/known-limits.md).

## Roadmap

Completed work and the ordered UI, CI and release plan live in
[docs/roadmap.md](https://github.com/rapiddweller/archkeel/blob/main/docs/roadmap.md).
Items remain planned until their listed evidence exists.

## License

MIT © 2026 Rapiddweller Asia Co., Ltd.

Maintained by [Alexander Kell](https://github.com/ake2l).
