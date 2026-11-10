# AD-352 The native TypeScript collector equals the Python one and is the bundled producer

**Status.** Accepted. Epic #880, PR 4.3a-5. It extends AD-340 and AD-344 and removes the gap of
AD-320.

**Decision.**
1. The reply of `archkeel-typescript-collector` equals the reply of the unmodified Python
   collector in every field: files, inputs, evidence, targets, capabilities, the seven sections,
   gaps and coverage. The script dependencies are ported (`script_*.rs`, `std_globals.rs`,
   `script_vendor.rs`). The gap "Script-global dependencies are not examined by the native
   collector" is no longer written. `script-globals-v1` is declared when Python declares it.
2. Each import-bearing node of the tree ends as a record or a gap. A node with neither is one
   `collection_gap`, `unextracted: n import-bearing node(s) of <file> have no record and no gap`
   (`imports.rs`, `check_extracted`). A node in a repaired part has the gap of the syntax error.
   The test binary can skip one reference on purpose (`plant.rs`); the release binary cannot.
3. The oracle `tests/native_oracle.py` is deleted. The native tests compare with `collect.collect`.
   The verdicts equal on the four fixtures and the 53 demo variants.
4. `ProducerKind.BUNDLED` is the native collector of this package. A platform wheel carries the
   binary and `<binary>.sha256` (`native/hatch_build.py`). `observer_for` gives the TypeScript
   scan this binary when both files are there, with the digest as its pin and the version check of
   AD-319. Without the pair the Python collector runs, as before. A `collector_argv` stays
   `external` or `pinned` whatever the install holds. Observation schema 2.10.0 allows `bundled`.
5. `bundled` is trusted like `python`: it can give PASS. The member inventory proof accepts the
   runtime of a bundled binary (it demanded Python 3.11, which the Rust runtime cannot declare).
   A binary of the install may lie inside the scanned root, for example in `.venv`; a pinned
   collector may not.

**Reason.** Zero differences against Python is what lets the host trust the binary. The invariant
turns a bug in the extraction into UNKNOWN. Python gave the proof to its own runtime only; the
host knows from the launch which producer it started, so the kind decides, not the reply.

**Cost.** Python asks, for each use of a global, a question over every file. Here indexes answer
them (`script_project.rs`), and nine project shapes bound the ratio of 2n to n
(`test_collector_native_script_deps_scaling.py`).

**Not done.** The strict xfails that empty a section of a reply stay: the host takes a declared
and empty section as complete. The invariant covers a lost node of the native collector; the wire
closes the rest with protocol 10. The native binary is not the default for a source checkout.

**Rejected.** A runtime check on the reply instead of the launch. An unpinned binary in `PATH`. A
digest inside the binary: it cannot vouch for its own file.

**Check.** `tests/test_collector_native_script_deps.py` (grid, vendors, mutated projects),
`test_collector_native_unextracted.py`, `test_collector_bundled_launcher.py`,
`test_collector_native_verdicts.py`, the golden replies with the native producer.
