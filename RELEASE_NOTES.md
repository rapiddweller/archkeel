# Codekeel 0.1.0

Codekeel adds deterministic architecture evidence to AI-assisted code review.
It checks whether a repository remains observable, follows its architecture
contract, and matches a change declaration published before submission.

## Highlights

- Run as a standalone Python package with the bundled analyzer.
- Define scan roots, namespace, and contract in `codekeel.toml`.
- Generate canonical `architecture.json` evidence with `codekeel report`.
- Review the same evidence in a self-contained `interactive.html` report.
- Compare accepted and candidate commits with `codekeel check`.
- Detect forbidden imports, cycles, private crossings, typing regressions,
  unresolved-call regressions, coverage loss, and changed finding fingerprints.
- Keep scan completeness, contract compliance, and expectation fulfillment as
  three separate verdicts.
- Return stable exit codes: `0` for pass, `1` for rejection, and `2` when the
  result cannot be verified.
- Validate declaration order from supplied host records or GitLab merge-request
  evidence.

## Install

Codekeel requires Python 3.11 or newer.

```bash
python -m pip install codekeel==0.1.0
codekeel --help
```

## Quick start

Add `codekeel.toml` to the repository:

```toml
[scan]
roots = ["src/example"]
namespace = "example"
contract = "architecture-contract.json"
```

Generate architecture evidence:

```bash
codekeel report --root . --output architecture.json
```

The command writes `architecture.json` and a portable `interactive.html` review
surface beside it.

## Current scope

- Python repositories are supported.
- `report` and `check` are available.
- `accept` is a placeholder and returns exit `2`.
- GitHub is used for distribution and CI; declaration-order retrieval currently
  has a GitLab adapter. Portable host records can be supplied explicitly.

See the [README](https://github.com/rapiddweller/codekeel) for the full protocol,
configuration, check command, and report preview.
