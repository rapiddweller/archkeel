# AD-1121: `report --format markdown` renders the topology as a guide

Status: accepted. Part of #679. Builds on AD-265 (the first guide, #695) and AD-432 (the Rust core decides).

## Why

Readers ask what each component owns and forbids, and which dependencies the contract declares. The answer is in
the contract JSON. Reading it by hand is slow.

The first guide (AD-265, #695) read the contract in Python. #1131 deleted the Python core, and the guide went with
it. A Python reader of the contract would put contract logic back in the shell. AD-432 forbids that.

## Decision

1. `archkeel report --output FILE --format markdown` writes a Markdown guide. The format choice is `markdown`,
   next to `html` and `json`.
2. The option turns on the topology section of the core frame (`options.topology`). The shell asks the core for the
   section. The shell does not read `architecture-contract.json`.
3. `src/archkeel/cli/core_guide.py` renders the decoded `Topology` from `core_topology.py`. It holds no rule, no
   verdict and no contract parse. Its output depends only on the topology. The same frame gives the same bytes.
4. The guide shows, in this order: the completeness of the frame, each component (status, layer, parent, packages,
   responsibilities, forbidden responsibilities, public interfaces, planned public interfaces), each `requires`
   entry with its reason and observed import count, and each `layer_order` rule.
5. A topology that the budget cut, or that has gaps, says so. It lists the gaps and the counts of the listed rows.
6. The shell contract gets the component `SHELL-GUIDE` (layer `present`, module `archkeel.cli.core_guide`). It
   requires `SHELL-DISPLAY` for the typed topology. `SHELL-COMMANDS` requires `SHELL-GUIDE` for the write of a report.
   The renderer reads only `Topology`: the other types of `core_topology` are not public in `SHELL-DISPLAY`.
6. `--format markdown` needs `--output`. Without it, the existing refusal applies.

## Rejected

- A Python `archkeel guide` that parses the contract. It repeats #1131.
- A Markdown renderer in `native/report`. It is correct for a later change, but it is larger and needs a Rust lane.
- A new command. `report` already writes the frame and the page. An option extends it, and the help text changes
  by one line.

## Effect

No verdict changes. No exit code changes. The `report` help lists `markdown`. `--format html` and `--format json`
do not change.

## Not done yet

- The guide does not show rules and their decision status. The Python shell does not decode the `explain` part of the
  frame. A later change can add a rule table from that part.
- The guide does not show the declared dependency graph. It lists the `requires` rows as text only.
- `init` does not write the guide.

## Checks

`tests/test_core_guide.py`: the pinned bytes of a complete fixture topology, the bytes of an incomplete one, the
same bytes on a second call, and the `--format markdown` option that turns on the topology.
Run on ArchKeel's own contract and on a Common Engine copy: see the pull request text.
