# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass CI and review.

## Set up

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
```

`.python-version` pins 3.11.12: CI runs the gate on it, and the saved self-observation records it.
The runtime test in `make check` also starts `python3.12`, so 3.12 must be on your `PATH`.
Flow browser tests require Node.js 22; CI and release builds install that pinned major version.

## Before you push

```bash
make ci BASE=origin/main                 # policy, release checks, TypeScript, browser and Mermaid
```

Policy validation runs first. `BASE` also checks widenings and amendments; CI pins the PR base SHA.
Without `BASE`, `make gate` validates only the checked-out policy before release checks.
CI splits this command into `make ci-check` and the parallel `make mermaid` job.
The Windows/Python/Node matrices remain separate CI checks. Obsolete PR runs cancel automatically;
main runs stay independent. The main check has a 60-minute cap, not a performance guarantee.

Every push to `main` also builds and publishes the [current architecture report](https://rapiddweller.github.io/archkeel/).
PRs run the same report build, Pages configuration check and artifact upload as Main.
Only the separate Main deployment job receives publishing permissions and consumes that artifact.
Both jobs run independently of the test jobs and path filters; PRs never deploy.
Reports retain FAIL and UNKNOWN findings. A failed report build leaves the published report intact.
Pages jobs run serially, and superseded revisions do not replace the current Main report.
GitHub Pages must use **GitHub Actions** as its publishing source.

Run `make report-pages` to generate the same site in `test-artifacts/pages/`: the overview,
shared detail page, canonical JSON and a small index redirect opening the dark theme.

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
