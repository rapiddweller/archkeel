# AD-362 A one-shot command collects cycles less often

**Status.** Accepted. It refines AD-324 for issues #1023 and #880.

**Decision.**
1. `main` in `cli/__init__.py` calls `gc.set_threshold(50_000, 20, 100)` once, for every command
   except `studio`. The Studio process keeps the default thresholds.
2. The encode-time `without_cycle_collection` guard of #1019 is removed. With the thresholds set,
   the run is not slower with the guard than without it.
3. `raw_fields` returns `{}` for a dataclass without fields. `_graph_payload` encodes
   `component_intents` once. The output bytes do not change. `member_inventory` keeps `asdict`: it
   would need an import of `codec_wire` that makes a component cycle in `ir`.

**Problem.** The garbage collector took 18 to 27 % of each native run. A one-shot command keeps
its model until it exits, and each full collection scans all of it again.

**Measurement.** Median of 3 to 5 interleaved runs, load 18 to 44 on 18 cores, excalidraw, main
`b5e3b11` against the PR `8f32bb4`:

| path | wall | peak |
|---|---|---|
| C native (default) | 27.0 to 23.5 s | 1834 to 1836 MiB |
| D native with store (opt-in) | 26.4 to 24.9 s | 2015 to 2213 MiB (host 1555 to 1750) |
| B Python | 104 to 105 s | 1761 to 1869 MiB |

On C, 2 of 5 PR runs reached 1918 MiB (+4.5 %): the peak depends on when a full collection runs.
K-python-realworld 3.7 to 3.4 s, golden fastapi-encoders 2.85 to 2.78 s, peaks unchanged.
`(100_000, 50, 100)` and `gc.freeze()` after the imports gave no better result. The middle setting
`(10_000, 15, 50)` was measured and does not trade better.

On the default native path the peak stays within the 5 % limit of the 4.4 gate. The opt-in store
path was 9.8 % above B before this change and is 20.6 % above B with it. The store does not
become the default until it is not fatter than B (step 5 of the order in #880).

**Rejected.** `gc.disable()`: a long run with cyclic garbage grows without bound (AD-318).
Thresholds in the Studio process: it lives for days and frees the models of old sessions.

**Limit.** A caller that runs `main` in its own process keeps the new thresholds after it returns.
Tests that call `main()` in the pytest process leave them set; that is accepted, because a test
that depends on collection calls `gc.collect()` first.

**Tests.** `tests/test_cli_gc.py`, `tests/test_host_memory.py`.
