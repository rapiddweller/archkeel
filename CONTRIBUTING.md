# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass CI and review.

## Set up

Install [uv](https://docs.astral.sh/uv/) and the two Python versions CI runs, 3.11.12 and 3.12.10:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
```

## Before you push

```bash
make check                              # Ruff, strict mypy, pytest and Archkeel's self-check
uv run archkeel validate --root . --json  # Archkeel's own contract, exit 0
```

## Regenerate the self-observation

`tests/test_self.py` runs `archkeel report` on this repository and compares the result with the
saved run in `fixtures/D-self`. Any change under `src/`, to `architecture-contract.json` or to the
architecture pages moves that run: the source or checker digest changes, and the test fails with
`fixtures/D-self is stale`. Regenerate it and commit it on its own:

```bash
make self-observation
git add fixtures/D-self
git commit -m "Regenerate the self-observation after <your change>"
```

Two branches that both regenerate conflict in these files. Rebase and run `make self-observation`
again instead of resolving the JSON by hand.

## A behaviour change carries its decision

- **Test first.** Add the test that shows the issue, see it fail, then make it pass.
- **Record the decision.** A change in behaviour gets an `AD-<n>` entry in
  [docs/architecture/archkeel.md](docs/architecture/archkeel.md) with its reason, the rejected
  alternatives, its limit and the tests that check it, and a row in
  [docs/roadmap.md](docs/roadmap.md). Update every document that describes the old behaviour.
- **Keep the contract true.** A new module needs a component in `architecture-contract.json`, and a
  new import between components needs a `requires` entry with its reason. Never widen a rule to
  make a check pass.
- **Commit messages** start with an imperative sentence and explain why in the body.

A small fix, such as a documentation correction, needs only the test and the regenerated
self-observation when it touches `src/`.
