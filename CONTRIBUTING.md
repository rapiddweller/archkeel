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

## Before you push

```bash
make check                              # Ruff, strict mypy, pytest and Archkeel's self-check
uv run archkeel validate --root . --json  # Archkeel's own contract, exit 0
```

## Regenerate the self-observation

`tests/test_self.py` runs `archkeel report` on this repository and compares the result with the
saved run in `fixtures/D-self`. A change to Python code under `src/` or to an architecture contract
(`architecture-contract.json` or an inside under `src/`) moves that run, and the test fails with
`fixtures/D-self is stale`. Documentation does not. Regenerate it and commit it on its own:

```bash
make self-observation
git add fixtures/D-self
git commit -m "Regenerate the self-observation after <your change>"
```

Two branches that both regenerate conflict in these files. Rebase and run `make self-observation`
again instead of resolving the JSON by hand.

Only regenerate when the test says so: every regeneration also records the current commit, so an
unneeded one rewrites `architecture.json` and conflicts with other branches for nothing.

## A behaviour change carries its decision

- **Test first.** Add the test that shows the issue, see it fail, then make it pass.
- **Record the decision.** A change in behaviour gets an `AD-<n>` file under
  [docs/architecture/decisions/](docs/architecture/decisions/) with its reason, the rejected
  alternatives, its limit and the tests that check it, an index row in
  [docs/architecture/archkeel.md](docs/architecture/archkeel.md), and a row in
  [docs/roadmap.md](docs/roadmap.md). Update every document that describes the old behaviour.
- **Keep the contract true.** A new module needs a component in `architecture-contract.json`, and a
  new import between components needs a `requires` entry with its reason. Never widen a rule to
  make a check pass.
- **Commit messages** start with an imperative sentence and explain why in the body.
