# AD-406 The core runs the TypeScript collector in its own process

**Status.** Accepted. Epic #880, issue #1095 slice 1, lead decision L-74. It follows AD-390 and
AD-399. It closes the entry conditions (a) and (b) of #1099 for the in-process TypeScript path.

**Decision.**
1. New crate `archkeel-collect` between `archkeel-core` and the collectors. It is the only crate
   that names a language. One function, `scan`, takes the scan identity and gives the validated
   reply and the contract bytes, or a `Refusal` that names a part. No plugin and no trait.
2. `archkeel-typescript-collector` gets a library target. The binary is a thin wrapper and
   writes the same bytes. The library gives `typed_reply`: the same `gather` and the same
   producer of the records, with the typed sink of the wire (`archkeel_wire::typed`).
3. The store gets a second front door, `ingest_typed`. It runs the one validation function of
   the byte door (`validated`); nothing else makes an `Ingested`. The decode holds no value
   check: the one such check (an analyzer failure has the area `analysis_coverage`) is
   `Record::invariants`, which `validated` runs for both doors. The store makes no producer
   claim (another adapter name is accepted, as in the Python codec).
4. New request kind `archkeel-core scan`, protocol `archkeel-core-scan-1`. It carries `root`,
   `config`, `git_head` and `dirty`, and no reply, digest, root list or trust field
   (`deny_unknown_fields`, exit 2). `archkeel-collect` reads the configuration and the contract,
   checks the paths as `load_config` does, derives the request of the shell (8.0.0, or 9.0.0
   with the test scope) and runs the collector. The core reads the inside contracts through
   the same reader, in the rounds and with the bounds of the shell (AD-379).
5. Trust: `Producer::Trusted` comes from the fact that the core ran the linked collector itself
   (`scan::in_process`). The reply must have the profile that ran, name its adapter and have the
   code digest of the build; each of the three has its own test. `check::stage_one_shell_trust` stays the only trust path of the check
   request; the scan request takes no reply bytes at all.
6. Shell. With `--native-core`, a TypeScript `report` with the bundled collector sends the scan
   request first. The shell compares the derived request with the request that it sent to its
   own collector, field by field; a difference is a named gap. Stage 1 stays on: Python decides
   the same run and a difference is exit 2. A frame that names a part sends the run to the check
   request. `check` stays on the check request: its contract comes from Git (AD-399).
7. Configured collectors and the Python, Rust and Dart profiles are refused by name (`collector`,
   `profile`); the shell does not send them a scan request. Self-contract: only `core` uses
   `collect`; `collect` uses only facts, store, wire and the collectors; a collector uses no store
   and no core-side crate. Each direction is a `NATIVE-NO-*` rule that fails also with a
   matching `requires` entry.
8. #1099 (a): the wheel builds the whole workspace without a feature, and `cargo tree` shows the
   collector without `dump`. A build with a test feature is a refusal (`build`), because `dump`
   reads planted faults from the environment. The code digest stays the digest of the sources.
9. #1099 (b): a survey charges each directory entry before the collector starts: more than
   100 000 entries, a directory deeper than 256 levels or more than 1 GiB of files is a refusal
   (`work budget`). It follows no symlink. The collector runs on a thread with a 256 MiB stack.
   A panic of a test build is a refusal. In the release build a panic aborts the core, as a stack
   overflow or an allocation failure does. The shell stops the core after 600 s and refuses each
   exit other than 0 and 3, so a dead core is exit 2, never PASS.

**Reason.** A reply that passes through the shell is the word of the shell (AD-390). Stage 2
needs facts that the core made itself.

**Rejected.** The core spawns a verified binary (the digest beside it proves nothing). Bytes in
a buffer. A trust field in the scan request. The core runs `git` (`PATH` would choose it).

**Limit.** The shell still gives `root`, `config` and `dirty`. The core reads `HEAD` and refuses
another `git_head`, but it takes `dirty` as provenance; only an unknown state changes a verdict,
and the request cannot carry one. The survey bounds the repository, not the work inside the
collector. No byte of output changes and no core starts without the switch.

**Needed before stage 2.** (1) Zero rules must give UNKNOWN: `report::rule` writes a PASS frame
with zero rules (`native/report/src/ruling.rs`); today the shell refuses that frame. (2) A memory
bound on the scan path: one 3 MB file of nested parentheses takes 1.36 GiB, six such files
3.69 GiB (release, review of #1107); the survey bounds entries and bytes, not this work.
**Stage 2 also needs.** A lead decision to stop the Python run. Work budgets inside the
collector. `dirty` from the core. `check` with the base reply and the contract from Git in the
core. The native evidence rendering. The other three profiles.

**Tests.** `native/collect/src/*_tests.rs`, `native/core/src/scan_tests.rs`,
`native/wire/src/typed_tests.rs`, `native/store/src/validate_tests.rs`,
`tests/test_cli_native_core_scan.py`, `tests/test_native_self_contract.py`,
`tests/test_native_self_rules.py`.
