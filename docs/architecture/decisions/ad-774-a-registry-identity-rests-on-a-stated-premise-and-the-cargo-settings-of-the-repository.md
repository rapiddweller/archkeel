# AD-774 A registry identity rests on a stated premise and the Cargo settings of the repository

**Status.** Accepted (lead decision on #1518: option C plus the in-repository part of option B, after the owner pattern of #1546 and AD-788). Part of #880, closes #1518. It amends AD-424 (review B2 and its open false PASS) and AD-704.

**Reason.** The models of AD-424 read `#[derive(Serialize)]` of serde 1.0.229, and the reviewed `macro_rules!` of registry crates, by the identity that `Cargo.lock` records: the crates.io source and the checksum. A `[source.crates-io] replace-with` takes the crate from another directory. Its `.cargo-checksum.json` can state the checksum of the lock, so `cargo check --locked --offline` builds it. In the plant of #1518, the replacement derive expands to `crate::b::secret()` in `a`, and `NO-A-TO-B` gave PASS. Before, any Cargo configuration below a scan root or on its path to the repository root withheld every model, whatever it held, and a replacement in `$CARGO_HOME` was not seen at all.

**Decision.**
1. **Premise (C).** A Rust scan in which a crate keeps a proven locked registry crate states the premise "registry crates are built from the identity that Cargo.lock records; no outside source replacement" (`scope_premise`, AD-540). The JSON key `premise`, the text line `Assumption:` and the report show it wherever they show the premise of a scan. The premise seam of #1634 is not merged yet; it reads the same field.
2. **Settings of the repository (B, inside the snapshot).** The collector reads each `.cargo/config.toml` and `.cargo/config` at any level of the repository, except below `.git` and `node_modules`. It also reads below cache markers, as amended by [AD-902](ad-902-a-cache-marker-does-not-bound-cargo-configuration.md).
   - A table `[source.crates-io]` (a replacement of crates.io) or a non-empty `paths` override withholds the proof of every registry crate.
   - A `[patch.<registry>]` entry withholds the crate that it names (its `package` key when it renames).
   - In the manifests of the crate and its workspace, a `[patch]` entry and a `[replace]` entry withhold the crate that they name. A package ID spec whose name the scan cannot read withholds every crate.
   - A configuration that does not parse, a `.cargo` link, an unreadable directory, a directory link and a walk beyond depth 128 or one million entries withhold every crate.
   - A configuration without these settings (`[build]`, `[alias]`) keeps the proof. Before, any configuration withheld every model.
3. A modeled derive whose library or implementation crate is withheld keeps its pair gap (UNKNOWN). One more gap of its module names the setting, the file and the line: "A replacement of crates.io in crates/.cargo/config.toml:2 may build the registry crate serde from other code than Cargo.lock records: its derive has no identity proof". A reviewed registry `macro_rules!` of a withheld crate keeps its unread-expansion gap.
4. Settings outside the repository (`$CARGO_HOME`, `CARGO_*` variables, `--config`, the machine that builds) are not read. The result of a snapshot does not depend on the machine; the premise states what it assumes about them.

**Why it is sound.** Inside the repository, every setting that can change the code of a locked registry crate withholds the proof of that crate, and a setting that the scan cannot read withholds every crate. Outside the repository, the PASS is no plain PASS: it holds under the printed premise, as a PASS under a declared door reach does (AD-664).

**Price.** A scan that has a locked registry crate prints one more premise line. The native self-check rows and gaps do not change (64 PASS, 28 UNKNOWN, 1279 pinned gaps on `6b8e007b4`), and its frame now carries the premise. The frozen Serde and itoa workspaces have no locked registry proof: no premise, no new gap, and the same rows.

**Rejected.**
- Read `$CARGO_HOME` and the environment (option B outside the repository): the same snapshot would give another result on another machine, and `--config` stays unseen.
- Withhold every registry model (option A): native drops from 92 PASS with 0 gaps to 0 PASS, 92 UNKNOWN, 5885 gaps, measured on `157dc8851`.
- Keep withholding every model for any configuration: a `[build]` table changes no registry crate.

**Tests.** `tests/test_collector_false_pass_rust_registry_replacement.py`: the replacement in `crates/.cargo/config.toml` gives UNKNOWN with a gap that names `crates/.cargo/config.toml:2` and no premise. The same replacement in `$CARGO_HOME` gives PASS with the premise. A configuration with only `[build]` keeps PASS. `cargo check --locked --offline` builds both replacement plants. `registry_overrides_tests.rs` covers the forms of point 2, and `known_derive_tests.rs` covers the depth bound and the `.cargo` link.
