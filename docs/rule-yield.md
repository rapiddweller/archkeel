# Measure rule evidence

Use a clean Git snapshot with `archkeel.toml`. Write outside that repository:

```bash
make rule-yield ROOT=/path/to/pinned-repository OUTPUT=build/yield.json
```

For a released analyzer or candidate, run the same tool with that installation's
Python: `<runtime>/bin/python tools/rule_yield.py --root <snapshot> --output <file>`.
Keep the Python version, source and contract unchanged. The output binds their
digests, package version and tool digest; `.architecture.json` preserves the raw scan.

Each declared rule reports its existing aggregate assessment status, violation
records and UNKNOWN by cause. Assessment PASS is never a positional pass count.
Non-boundary per-predicate passes remain `null`.

Version2 captures existing boundary producer verdicts and population receipts.
Reconciled populations publish actual totals, including all-safe scopes without
a limit record. A true position PASS requires neither violation nor undecidability;
accepted broad/opaque allowances count separately. VIO, UNKNOWN and allowances
can overlap; these counts must not be added as exclusive categories.
Ledger identities retain scope, symbol, occurrence and inherited method origin.
Receipt-only ambiguous facade positions remain UNKNOWN. Missing capture leaves
pass counts `null`; no subtraction invents them. Missing/repeated receipts retain
readable observed positions. The profiled scan must match plain canonical JSON bytes.

Population reconciliation does not prove full scope closure. Unresolved routes,
missing subjects and incomplete scans remain explicit. Unscoped API limits retain
their actual module/subject in a separate global balance; they are not attributed
to every boundary rule and do not erase proved position counts.

Three normal scans supply a median. A separate profiled scan captures each existing
evaluator's inputs. Independent warm `cProfile` replays retain those source facts
and scope, selecting one rule. Runtime is `null` if replay changes that rule's
findings. Replay timings include profiling overhead; they are neither exclusive
nor additive scan time. Capture overhead is reported separately.

[Historical version 1 CE/EE evidence](evidence/rule-yield/README.md) compares released
0.8.4 with the earlier #205 candidate. This optional command adds no score or metric gate.
Issue #218's full acceptance still needs an explicit EE boundary contract,
unsupported per-predicate pass/runtime evidence and the post-release comparison.
