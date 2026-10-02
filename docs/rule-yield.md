# Measure rule evidence

Use a clean Git snapshot with `archkeel.toml`. Write outside that repository:

```bash
make rule-yield ROOT=/path/to/pinned-repository OUTPUT=build/yield.json
```

For a released analyzer or candidate, run the same tool with that installation's
Python: `<runtime>/bin/python tools/rule_yield.py --root <snapshot> --output <file>`.
Keep the Python version, source and contract unchanged. The output binds their
digests, package version and tool digest; `.architecture.json` preserves the raw scan.

Each declared rule reports violation records and UNKNOWN by cause. A boundary
position can carry both. Published position totals are retained where present;
missing totals and decided passes are `null`, because the IR lacks a complete
per-position pass/violation/UNKNOWN ledger. No subtraction invents passes.

Three normal scans supply a median. A separate profiled scan captures each existing
evaluator's inputs. Independent warm `cProfile` replays retain those source facts
and scope, selecting one rule. Runtime is `null` if replay changes that rule's
findings. Replay timings include profiling overhead; they are neither exclusive
nor additive scan time. Capture overhead is reported separately.

[Pinned CE/EE evidence](evidence/rule-yield/README.md) compares released 0.8.4 with
one corrected candidate. This optional command adds no score or metric gate.
Issue #218's full acceptance remains pending the CE blocker release, an explicit
EE boundary contract and complete decided-pass evidence.
