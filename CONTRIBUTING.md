# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass CI and review.

## Set up

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
make dart-setup
```

`.python-version` pins 3.11.12: CI runs the gate on it, and the fresh self-observation records it.
The runtime test in `make check` also starts `python3.12`, so 3.12 must be on your `PATH`.
Flow browser tests and Mermaid rendering require Node.js 22; CI installs it for these tools.
Dart checks need an SDK in `>=3.9,<4`; `make dart-setup` prepares the pinned native Analyzer.

## Before you push

```bash
make ci-pr-check BASE=origin/main        # policy, lint, types and representative Core tests
make ci-pr-report-check                  # browser sample for report changes
```

Policy validation runs first. `BASE` also checks widenings and amendments; CI pins the PR base SHA.
Without `BASE`, the local gate validates only the checked-out policy.
PRs and Main pushes run the change-selected core and report regression checks; Mermaid checks
follow Markdown changes. The report sample includes the real nested-Python route regression,
renderer, drag/async and independent-Target checks. Samples do not replace testing the behavior
you change.

The scheduled **Full verification** workflow runs the complete `make ci` gate, report timing and
browser proof, gallery generation, plus Windows/Python, TypeScript and Dart SDK/OS matrices. It
also supports manual dispatch. Release tags call that same full workflow before package build and
publication. Use `make ci BASE=origin/main` locally for the complete gate.

The [published architecture report](https://rapiddweller.github.io/archkeel/) updates after a
successful scheduled or manual full verification on Main. Reports retain FAIL and UNKNOWN
findings; a failed build leaves the published report intact. GitHub Pages must use **GitHub
Actions** as its publishing source.

Run `make report-pages` to generate the same site in `test-artifacts/pages/`: an entry page,
the current report and the Python, Dart and TypeScript demos with shared detail pages and canonical
JSON. Demo links open in the dark theme; `/demos/` leads to the gallery.

## Inspect the self-observation

Tests generate one fresh report per session and share it across workers. They check
coverage, architecture rules, interfaces and declared budgets against the current code.
No generated result or provenance snapshot needs to be committed.

To inspect the same repository locally:

```bash
make self-observation
```

This prints the result and writes JSON/HTML to ignored `test-artifacts/self-observation/`.
Architecture contracts, baselines and amendments remain reviewed source files.

## A behaviour change carries its decision

- **Test first.** Add the test that shows the issue, see it fail, then make it pass.
- **Record the decision.** A change in behaviour gets an `AD-<n>` file under
  [docs/architecture/decisions/](docs/architecture/decisions/) with its reason, the rejected
  alternatives, its limit and the tests that check it, an index row in
  [docs/architecture/archkeel.md](docs/architecture/archkeel.md). Update documents that describe
  the old behaviour. Keep the decision under the tested 70-line limit. The
  [roadmap](docs/roadmap.md) lists open work only.
- **Keep the contract true.** A new module needs a component in `architecture-contract.json`, and a
  new import between components needs a `requires` entry with its reason. Never widen a rule to
  make a check pass.
- **Commit messages** start with an imperative sentence and explain why in the body.

Contract or baseline budget widenings require a reviewed v2 amendment binding both policies. Use `make ci BASE=<base-commit>` to check them before the full gate. A changed amendment must match exactly; multiple changed records fail. `decided_by` and `rationale` are free text, not authenticated approval.

## Update the agent skill

Edit [skills/archkeel/SKILL.md](skills/archkeel/SKILL.md). The CLI asset links to this source.
Run `make plugin-directory` to refresh the committed compact plugin; do not edit its copy.
