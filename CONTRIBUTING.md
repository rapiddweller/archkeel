# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass CI and review.

## Set up

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
make dart-setup
```

`.python-version` pins 3.11.12: CI runs the gate on it, and the saved self-observation records it.
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
PRs select Core and report samples by changed area; Mermaid checks follow Markdown changes.
These samples do not replace testing the behavior you change. Rare or platform-specific
regressions may first surface on Main. The PR check has a 15-minute cap.

Every Main push runs the full `make ci`: all tests, build/smoke, TypeScript demos, report timing,
browser acceptance and Mermaid. Native collector matrices also run on Main, including
Linux/Windows and Dart 3.9/3.12. Use `make ci BASE=origin/main` locally for that full scope.
Obsolete PR runs cancel automatically; Main runs remain independent with a 60-minute check cap.

Every push to `main` also builds and publishes the [current architecture report](https://rapiddweller.github.io/archkeel/).
PRs run the same report build, Pages configuration check and artifact upload as Main.
Only the separate Main deployment job receives publishing permissions and consumes that artifact.
Both jobs run independently of the test jobs and path filters; PRs never deploy.
Reports retain FAIL and UNKNOWN findings. A failed report build leaves the published report intact.
Pages jobs run serially, and superseded revisions do not replace the current Main report.
GitHub Pages must use **GitHub Actions** as its publishing source.

Run `make report-pages` to generate the same site in `test-artifacts/pages/`: an entry page,
the current report and the Python, Dart and TypeScript demos with shared detail pages and canonical
JSON. Demo links open in the dark theme; `/demos/` leads to the gallery.

## Regenerate the self-observation

`tests/test_self.py` runs `archkeel report` on this repository and compares the result with the
saved result and provenance in `fixtures/D-self`. The full JSON and HTML are generated once
per test session and shared by local workers. A change to Python code under `src/`,
`pyproject.toml`, or a contract (`architecture-contract.json` or an inside contract) moves
that run, and the test fails with
`fixtures/D-self is stale`. Documentation does not. Regenerate it and commit the compact evidence:

```bash
make self-observation
git add fixtures/D-self/result.json fixtures/D-self/provenance.json
git commit -m "Regenerate the self-observation after <your change>"
```

Two branches that both regenerate conflict in these files. Rebase and run `make self-observation`
again instead of resolving the JSON by hand.

`make self-observation` also writes the ignored full JSON and HTML locally. Provenance keeps
only the checker and observation digests; tests normalize Git HEAD/dirty and check all other content.
Only regenerate when the test says so.

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
