# Measure rule evidence

Use a clean Git snapshot with `archkeel.toml`. Write outside that repository:

```bash
make rule-yield ROOT=/path/to/pinned-repository OUTPUT=build/yield.json
```

To compare installations, run `tools/rule_yield.py` with each installation's
Python, keeping source, contract and Python version fixed. Output binds their
digests and tool identity; the `.architecture.json` companion preserves raw facts.

Read units before comparing counts:

- Boundary positions: actual producer verdicts and population receipts. PASS
  requires neither violation nor undecidability. Broad allowances are separate;
  VIO, UNKNOWN and allowance counts can overlap.
- Dependency, interface and requires imports: actual evaluator yields bound to
  original import IDs and completion evidence. These are predicate counts, not
  unique repository imports.
- Other evaluators: one observed-scope conjunction. A known violation makes it
  false once; incomplete evidence prevents PASS. This is not a per-child count.

Never add these units. Aggregate assessment PASS is not a positional pass count.
Missing producer proof keeps counts null; population reconciliation alone does
not prove scope closure. Unresolved routes, missing subjects and incomplete scans
remain explicit. Permissions are declarations without decision counts.

The profiled scan must match plain canonical bytes. Warm replay time is unavailable
if findings change, and includes profiling overhead; it is neither exclusive nor
additive scan time. See [tool implementation](../tools/rule_yield.py) for ledgers,
formats and runtime checks. This optional command adds no score or gate.
[Version 1 CE/EE artifacts](evidence/rule-yield/README.md) retain historical evidence.
