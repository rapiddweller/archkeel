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

**Measurement.** Median of 3 interleaved runs, native collector, Apple M5 Pro. excalidraw: 26.7 s
to 18.7 s, peak 1840 to 1907 MiB. Private TS app (910 files): 53.2 s to 38.6 s, peak 3152 to
3148 MiB. K-python-realworld and golden fastapi-encoders: no change beyond 0.1 s and 1 MiB.
`(100_000, 50, 100)` and `gc.freeze()` after the imports gave no better result.

**Rejected.** `gc.disable()`: a long run with cyclic garbage grows without bound (AD-318).
Thresholds in the Studio process: it lives for days and frees the models of old sessions.

**Limit.** A caller that runs `main` in its own process keeps the new thresholds after it returns.

**Tests.** `tests/test_cli_gc.py`, `tests/test_host_memory.py`.
