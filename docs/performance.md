# CLI validation time

## DATAMIMIC Community Edition

How long does a developer wait for a local contract check? This comparison times the installed
`archkeel validate --config FILE --json` process from launch through exit. It includes startup,
analysis and writing JSON to a pipe. It measures the whole command, including differences in
how much evidence each version collects and prints.

The benchmark covers the entire `datamimic_ce` production package at
[revision e1000a6e](https://github.com/rapiddweller/datamimic/tree/e1000a6eef55ae4d710c923116d6551f19436d53).
Both versions scanned 540 Python files (63,982 source lines) and passed the same `complete_assignment` rule, which
checks that every module has a declared owner. CE's existing contract requires a measurement
baseline on 4.0.1, so the timed runs used a separate one-rule contract. The production code
was unchanged.

| Installed CLI | Median | Min–max | Package ownership | Overall verdict |
| --- | ---: | ---: | --- | --- |
| 4.0.1, Python engine | 27.93 s | 27.88–28.25 s | PASS | PASS, exit 0 |
| 5.0.0-dev, Rust core | 1.18 s | 1.17–1.19 s | PASS | UNKNOWN, exit 2 |

The Rust core reported 59 collection gaps, including a runtime `eval(expression, …)`
and a comparison with `"__import__"`. The comparison is a gap in what the collector
can prove. It does not establish that CE executed a dynamic import.

### What the two builds resolve

The input contains 748 class definitions, 3,169 function and method definitions
(including 16 async definitions), and 3,408 import statements, counted from Python's AST.
One import statement can name several targets. The timed reports do not supply a
comparable count of resolved module-to-module import edges.

| Call-site inventory reported by each build | 4.0.1 | 5.0.0-dev |
| --- | ---: | ---: |
| Total counted | 14,744 | 16,391 |
| Reported as resolved | 11,140 | 0 |
| Partially resolved | 2,187 | 0 |
| Classified separately as builtin / external | No separate counts | 4,052 / 1,465 |
| Unresolved | 1,417 | 10,874 |

Python's AST contains 14,744 explicit call expressions. The Rust collector also counts
1,647 implicit decorator applications. Together they account for all 16,391 sites.

The 4.0.1 collector marked 11,140 sites as resolved. Of their target names, 4,594 start
with `builtins.`, 4,917 start with `datamimic_ce.`, and 1,629 have another prefix.
Within those 4,917 CE sites, 4,181 records include a source reference for the target. The other 736 lack that reference.
Each number counts call sites. Several sites can point to the same definition.
The Rust build reports builtin and external calls separately.

Two calls in this CE revision illustrate the difference between a name and a definition.

| Call in CE | What the source shows |
| --- | --- |
| [`IssueDefinition(...)`](https://github.com/rapiddweller/datamimic/blob/e1000a6eef55ae4d710c923116d6551f19436d53/datamimic_ce/errors/catalog/task_errors.py#L6-L12) | The import names a [class defined in CE](https://github.com/rapiddweller/datamimic/blob/e1000a6eef55ae4d710c923116d6551f19436d53/datamimic_ce/errors/catalog/definition.py#L14). |
| [`logger.debug(...)`](https://github.com/rapiddweller/datamimic/blob/e1000a6eef55ae4d710c923116d6551f19436d53/datamimic_ce/engine/runtime/tasks/flow/commands/echo_task.py#L27) | 4.0.1 gives the target a CE name. CE obtains [`logger` from `logging.getLogger`](https://github.com/rapiddweller/datamimic/blob/e1000a6eef55ae4d710c923116d6551f19436d53/datamimic_ce/engine/runtime/logging.py#L84). The binding alone leaves the implementation of `debug` open. |

### Follow-up on the same CE source

A separate Studio scan linked **3,548 call sites to 1,183 candidate declarations**.
Of those sites, **1,873** point into another module. **325** refer to methods on a receiver.
All 3,548 matched the qualified target that 4.0.1 reported at the same explicit call.
The declaration locations also matched definitions in CPython's AST.

The updated collector classified 156 more sites as builtin calls, for **4,208 builtins**
and **10,718 unresolved**. It still reported 59 collection gaps and zero proven internal calls.
CE's installation check inspects `sys.modules` outside the production scan root.
ArchKeel conservatively treats all 540 modules as exposed to possible writes.
This describes an assumption about bindings. See the [CE installation check](https://github.com/rapiddweller/datamimic/blob/e1000a6eef55ae4d710c923116d6551f19436d53/script/check_installed_authoring.py#L114-L136).

The Studio scan measures source navigation. The CLI timings above apply to the earlier
development build at `858cb6905`.

## Smaller fixtures

| Fixture | Rule results in both builds | 4.0.1 median (range) | 5.0.0-dev median (range) |
| --- | --- | --- | --- |
| F-architecture, Python test scope | 6 PASS | 227 ms (226–232) | 80 ms (79–83) |
| H-typescript-checkout | 1 PASS, 1 declaration | 210 ms (207–214) | 86 ms (84–88) |

Measured November 20, 2026, on one Apple M5 Pro, macOS 27.2 arm64, CPython 3.11.12.
The older wheel was PyPI 4.0.1. The unreleased 5.0.0 line was measured at
`858cb6905` using its bundled release-mode Rust core. Its wheel version was
`4.0.2.dev933+g858cb6905`. Each fixture had one warm-up per version, then eight measured
runs per version for CE and 12 for each small fixture, alternating which ran first. Each run started a fresh process.
Installation and builds took place before measurement.

Both displayed cases exited 0 and agreed on every rule ID and status. Four further fixtures
tested for inclusion (G-dart, J-compass, K-python-realworld and L-nest-realworld) had differing
rule results or lacked comparable output. Studio snapshot startup is a separate workload.

## Repeat the measurement

Install the two wheels in separate environments with the same Python. For CE, use a disposable
checkout of the revision linked above. Save these three files at its root and commit them
there so both engines see a clean Git tree.

**benchmark.toml**

```toml
[scan]
roots = ["datamimic_ce"]
namespace = "datamimic_ce"
contract = "benchmark-contract.json"
```

**benchmark-contract.json**

```json
{
  "schema_version": "3.3.0",
  "components": [
    {
      "id": "COMP-CE",
      "label": "ce",
      "role": "component",
      "packages": [
        "datamimic_ce"
      ],
      "responsibilities": [
        "Own the CE production package."
      ],
      "forbidden_responsibilities": [],
      "provenance": [
        "benchmark-architecture.md"
      ],
      "requires": [],
      "decided_by": "architect"
    }
  ],
  "rules": [
    {
      "id": "CE-ASSIGNMENT",
      "kind": "complete_assignment",
      "source": "datamimic_ce",
      "rationale": "Each module in the CE production package has one declared owner.",
      "provenance": [
        "benchmark-architecture.md"
      ],
      "decided_by": "architect"
    }
  ]
}
```

**benchmark-architecture.md**

````markdown
# CE benchmark architecture

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    ce
```
````

Save the script below outside the checkout. From CE's root, set `PYTHONHASHSEED=0` and run
`python /path/to/bench.py /path/to/old/archkeel /path/to/new/archkeel benchmark.toml 8`.
To repeat a small-fixture run, copy the fixture from ArchKeel revision `858cb6905` into its own
Git repository and commit it. Use `archkeel-tests.toml 12` for F-architecture and
`archkeel.toml 12` for H-typescript-checkout.

```python
import json
import statistics
import subprocess
import sys
import time

old, new, config, pairs = sys.argv[1:]
times = {old: [], new: []}
expected = None
for pair in range(int(pairs) + 1):
    for cli in ((old, new) if pair % 2 else (new, old)):
        start = time.perf_counter()
        run = subprocess.run([cli, "validate", "--config", config, "--json"],
                             capture_output=True, check=False)
        ms = (time.perf_counter() - start) * 1000
        data = json.loads(run.stdout)
        if cli == old:
            rows = {r["id"]: r["status"] for r in data["rule_assessments"]}
        else:
            rows = {k: v[1] for k, v in data["frame"]["rules"].items()}
        if config == "benchmark.toml":
            count = (data["coverage"]["files_parsed"] if cli == old
                     else data["frame"]["self_test"]["reply"]["files"])
            assert count == 540 and rows == {"CE-ASSIGNMENT": "PASS"}
            assert run.returncode == (0 if cli == old else 2)
        else:
            assert run.returncode == 0
        if expected is None:
            expected = rows
        assert rows and rows == expected
        if pair:
            times[cli].append(ms)
for cli, values in times.items():
    print(cli, "median/min/max (ms)", statistics.median(values), min(values), max(values))
```
