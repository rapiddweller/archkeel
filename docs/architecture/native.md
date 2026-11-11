# The native workspace

The Rust workspace in `native/` holds the collectors that read source for Archkeel.
Archkeel checks this workspace with its own Rust collector and the contract in
`native/architecture-contract.json` ([AD-335](decisions/ad-335-archkeel-checks-the-rust-of-native-with-its-own-contract.md)).
Run `make self-validate-native` to check it.

The contract has two levels. The crates are the base (`facts`, `wire`, `snapshot`, `store`, `build`). Each
collector crate is split into components by responsibility, and an arrow points down only:
the entry calls the flow, the flow calls the parts (discover, parse, resolve, records), and
the records component builds the records of the collector. Rule `NATIVE-REQUIRES-COMPLETE` allows only the
arrows in the contract, and rule `NATIVE-NO-MODULE-CYCLES` forbids a module cycle. No module is out of scope: the macro cycle of `archkeel-facts` ([#954](https://github.com/rapiddweller/archkeel/issues/954)) is gone since #961.
The old layer file and its test are removed (AD-327): a declared
Cargo dependency that no module uses is a crate edge, and the contract rejects it.

| Crate | Role | Uses |
|---|---|---|
| `archkeel-wire` | The collector wire: requests, replies and source identities. | `archkeel-facts` |
| `archkeel-snapshot` | The one owner of snapshot reads: POSIX paths, contained reads, the symlink rule and the size limit. | `archkeel-facts` |
| `archkeel-facts` | The one typed definition of each collector fact (AD-345). | no crate of the workspace |
| `archkeel-store` | Validates a reply once, keeps the facts and writes `architecture.json` (AD-346). | `archkeel-facts` |
| `archkeel-build-support` | The helper that the `build.rs` of each collector calls: the digest of the sources. | no crate of the workspace |
| `archkeel-dart-grammar` | Gives the Dart grammar: the vendored C parser of tree-sitter-dart 0.1.0, the grammar of the Python collector (AD-342). It does not parse. | no crate of the workspace |
| `archkeel-typescript-collector` | Reads TypeScript source. | `archkeel-wire`, `archkeel-snapshot`, `archkeel-facts`, `archkeel-build-support` |
| `archkeel-rust-collector` | Reads Rust source. | `archkeel-wire`, `archkeel-snapshot`, `archkeel-facts`, `archkeel-build-support` |

A collector crate never uses another collector crate. Only a collector crate uses a parser crate.
A grammar crate links a vendored C parser and gives its language; only a grammar crate depends on
`tree-sitter-language` (rule `NATIVE-EXTERNAL-TREE-SITTER-LANGUAGE`).
Clippy, `cargo deny` and the file size rule stay outside the contract
([AD-327](decisions/ad-327-rust-architecture-rules-are-measured-in-the-gate.md)).

## The dual run

The Rust model and evaluator (WP6 of #880) must give the verdicts and rows of the Python engine.
`make dual-run` compares a candidate engine with the recorded oracles in `tests/dual_run/`
([AD-360](decisions/ad-360-a-second-engine-is-compared-with-recorded-oracles-per-section-and-rule-family.md)).
A slice names what it owns:

```bash
make dual-run DUAL_RUN_ARGS="--sections modules,packages --families direction \
  --engine-command 'native/target/debug/archkeel-core dual-run'"
```

The engine command reads one JSON request on standard input: `protocol`, `case`, `root`,
`config`, `baseline`, `contracts`, `collector_argv`, `pinned`, `reply` and `sections`. It writes
one frame on standard output: `rules` (rule id to kind and status) and the columnar
`architecture` or the canonical `sections`. A failed or slow engine is a difference
(`--engine-timeout`, default 600 s). The sections and rule families are in
`tools/dual_run_schema.json`.
`python -m tools.dual_run serve-python` is the reference: it serves the Python engine. The
binary name in the example is a placeholder: no Rust engine exists yet.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    n_0["build"]
    n_1["facts"]
    n_2["rs-builder"]
    n_3["rs-edges"]
    n_4["rs-entry"]
    n_5["rs-flow"]
    n_6["rs-modules"]
    n_7["rs-reply"]
    n_8["rs-text"]
    n_9["rs-workspace"]
    n_10["snapshot"]
    n_11["store"]
    n_12["ts-declarations"]
    n_13["ts-discover"]
    n_14["ts-dump"]
    n_15["ts-entry"]
    n_16["ts-flow"]
    n_17["ts-input"]
    n_18["ts-parse"]
    n_19["ts-records"]
    n_20["ts-resolve"]
    n_21["ts-script-deps"]
    n_22["ts-scripts"]
    n_23["ts-sites"]
    n_24["ts-tree"]
    n_25["ts-walk"]
    n_26["wire"]
    n_10 --> n_1
    n_11 --> n_1
    n_12 --> n_17
    n_12 --> n_24
    n_13 --> n_10
    n_13 --> n_17
    n_14 --> n_1
    n_14 --> n_12
    n_14 --> n_16
    n_14 --> n_17
    n_14 --> n_18
    n_14 --> n_19
    n_14 --> n_23
    n_14 --> n_25
    n_15 --> n_0
    n_15 --> n_1
    n_15 --> n_10
    n_15 --> n_14
    n_15 --> n_16
    n_15 --> n_26
    n_16 --> n_1
    n_16 --> n_10
    n_16 --> n_13
    n_16 --> n_17
    n_16 --> n_18
    n_16 --> n_19
    n_16 --> n_20
    n_16 --> n_21
    n_16 --> n_25
    n_16 --> n_26
    n_18 --> n_12
    n_18 --> n_17
    n_18 --> n_22
    n_18 --> n_24
    n_18 --> n_25
    n_19 --> n_1
    n_19 --> n_12
    n_19 --> n_17
    n_19 --> n_18
    n_19 --> n_23
    n_19 --> n_25
    n_19 --> n_26
    n_2 --> n_1
    n_2 --> n_6
    n_2 --> n_8
    n_2 --> n_9
    n_20 --> n_10
    n_20 --> n_13
    n_20 --> n_17
    n_21 --> n_1
    n_21 --> n_10
    n_21 --> n_13
    n_21 --> n_17
    n_21 --> n_18
    n_21 --> n_19
    n_21 --> n_23
    n_21 --> n_25
    n_22 --> n_12
    n_22 --> n_17
    n_22 --> n_24
    n_22 --> n_25
    n_23 --> n_12
    n_23 --> n_17
    n_23 --> n_24
    n_24 --> n_17
    n_25 --> n_1
    n_25 --> n_12
    n_25 --> n_17
    n_25 --> n_23
    n_25 --> n_24
    n_26 --> n_1
    n_3 --> n_1
    n_3 --> n_10
    n_3 --> n_2
    n_3 --> n_6
    n_3 --> n_8
    n_3 --> n_9
    n_4 --> n_0
    n_4 --> n_1
    n_4 --> n_10
    n_4 --> n_26
    n_4 --> n_5
    n_5 --> n_1
    n_5 --> n_10
    n_5 --> n_2
    n_5 --> n_6
    n_5 --> n_7
    n_5 --> n_9
    n_6 --> n_10
    n_6 --> n_8
    n_6 --> n_9
    n_7 --> n_1
    n_7 --> n_10
    n_7 --> n_2
    n_7 --> n_26
    n_7 --> n_6
    n_9 --> n_10
```
