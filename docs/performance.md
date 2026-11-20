# CLI validation time

How long does a developer wait for a local contract check? This comparison times the installed
`archkeel validate --config FILE --json` process from launch through exit. It includes startup,
analysis and writing JSON to a pipe. It measures the whole command, including differences in
how much evidence each version collects and prints.

| Fixture | Rule results in both builds | 4.0.1 median (range) | 5.0.0-dev median (range) |
| --- | --- | --- | --- |
| F-architecture, Python test scope | 6 PASS | 227 ms (226–232) | 80 ms (79–83) |
| H-typescript-checkout | 1 PASS, 1 declaration | 210 ms (207–214) | 86 ms (84–88) |

Measured November 20, 2026, on one Apple M5 Pro, macOS 27.2 arm64, CPython 3.11.12.
The older wheel was PyPI 4.0.1. The unreleased 5.0.0 line was measured at
`858cb6905` using its bundled release-mode Rust core. Its wheel version was
`4.0.2.dev933+g858cb6905`. Each fixture had one warm-up per version, then 12 measured
runs per version, alternating which ran first. Each run started a fresh process.
Installation and builds took place before measurement.

Both displayed cases exited 0 and agreed on every rule ID and status. Four further fixtures
tested for inclusion (G-dart, J-compass, K-python-realworld and L-nest-realworld) had differing
rule results or lacked comparable output. Large-repository throughput and Studio snapshot
startup require separate measurements.

## Repeat the measurement

Use the fixtures from the measured revision and install the two wheels in separate environments
with the same Python. Copy each fixture into a temporary directory, initialize a Git repository
there and commit its files. From inside each fixture, run the following script with
`python /path/to/bench.py /absolute/path/to/old/archkeel /absolute/path/to/new/archkeel FILE`.
Keep the script outside the fixture. Use `archkeel-tests.toml` for F-architecture and
`archkeel.toml` for H-typescript-checkout.

```python
import json
import statistics
import subprocess
import sys
import time

old, new, config = sys.argv[1:]
times = {old: [], new: []}
expected = None
for pair in range(13):
    for cli in ((old, new) if pair % 2 else (new, old)):
        start = time.perf_counter()
        run = subprocess.run([cli, "validate", "--config", config, "--json"],
                             capture_output=True, check=True)
        ms = (time.perf_counter() - start) * 1000
        data = json.loads(run.stdout)
        if cli == old:
            rows = {r["id"]: r["status"] for r in data["rule_assessments"]}
        else:
            rows = {k: v[1] for k, v in data["frame"]["rules"].items()}
        if expected is None:
            expected = rows
        assert rows and rows == expected
        if pair:
            times[cli].append(ms)
for cli, values in times.items():
    print(cli, "median/min/max (ms)", statistics.median(values), min(values), max(values))
```
