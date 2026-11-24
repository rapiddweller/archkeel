# AD-1047 Rust dispatch gaps use compiler type reach

**Status.** Accepted. Owner decision 2026-11-22 (path B2). Amends AD-806 and AD-866. Stages 1 to 4 are built.

**Decision.** ArchKeel runs its own rustc driver on the scanned Cargo workspace with a pinned
toolchain. The driver writes type-reach facts for each module. The Rust collector drops a
trait-impl, destructor or receiver gap `a -> b` only when the facts prove that no MIR body of
`a` can hold a value of a self type of any impl in `b` that runs code, in every configuration
of the matrix. A rule that a dropped gap decides gives `PASS assuming rust_type_reach`, and only
when the contract declares the premise. Without facts, the gaps stay.

**Reason.** The syntax scan sees no types, so AD-806 gives a gap to every module that reaches `b`.
**Type reach of a module `a`.** The ADTs in the types of locals, calls, signatures, casts and constants of every
body in `a`, with closures, their field closure, hidden types of opaque types, generic instances that flow in, and
associated-type ADTs of reached impls. For each `dyn Tr` in reach, add each type that is coerced to `Tr`.

**Premises of a PASS (`rust_type_reach`).** This list is the one place of the premises. The contract declares the
premise `rust_type_reach`, and each PASS that a dropped gap decides names it.
1. Whole program. The scanned Cargo workspace is the whole program. No code outside the Rust build (C, assembly,
   `dlopen`, a plug-in) runs an impl of the workspace. Workspace code means the members of `cargo metadata`: a
   path dependency is foreign, wherever its directory is. The verifier refuses facts that name its files.
2. This target and this matrix. A cfg set that the matrix (default, no default features, all features, each feature alone) does not enable and a target other than this host are not seen.
   A PASS does not speak about that code. More than 16 features give no facts (`TooManyFeatures`). A `target_os = "windows"` case is stated, not tested.
3. The repository is trusted. `cargo check` runs its build scripts and proc macros, and `--offline` does not stop
   their network access.
4. The driver and the compiler are bound. The pinned rustc (`tools/rustc-facts/rust-toolchain.toml`) gives the
   same types as the toolchain of the project. The facts bind the `rustc -vV` text, the driver hash, the
   configuration, the `Cargo.lock` hash and the SHA-256 of each source file that rustc read. The collector checks each
   binding. A mismatch gives no facts, and the gaps stay.
5. Unsafe raw-pointer code is charged with the worst case. A value behind a raw pointer to `()`, `c_void`, an
   extern type or a number has no type here. A module, or an ADT of any crate, that holds such a pointer reaches each
   type that a pointer cast, a transmute or an address cast hid, and each type that calls outside the workspace took
   with that ADT in their signature. A round trip through an integer address (`ptr as usize`) is not seen, and a
   PASS does not speak about it.

**Stage 1.** `tools/rustc-facts` is the driver: a binary crate with no dependency, its own toolchain file
(`rustc-dev`) and `Cargo.lock`. It hooks `mir_built` and writes one file for each unit (renamed, closed by `end`). `native/collect` (`FactsTools::produce`) checks the toolchain, builds the driver
into the cache, and runs `cargo check --workspace --all-targets --offline --locked` for each configuration, with a
cleared environment and an empty `RUSTFLAGS`. `native/rust` (`Expected`) needs one file for each unit that Cargo names,
with a matching `build` line, and each scanned file with its hash. `native/facts` holds the typed cause `Unavailable`.

**Rejected.** SCIP (AD-1036): no temporaries, drops or coercions. Syntax-only reach: no inferred type. The driver in
`native/rustc-facts`: `extern crate rustc_driver` made the self-scan UNKNOWN; it lives in `tools/`.

**Stages 3 and 4.** `[scan] rust_type_reach = true` (Rust only) makes the core run `FactsTools::produce` and pass
a descriptor path to the Rust worker in `ARCHKEEL_TYPE_REACH`. `Filter` drops a trait-impl, destructor or receiver gap
when no config can run an impl of `b` from `a`. A `dyn Tr` counts as every implementer of `Tr` (class hierarchy). A pair
without facts for `a` stays. Any `Unavailable` cause adds one whole-scope gap with the exact reason (UNKNOWN). Contract
3.21.0 adds the premise `rust_type_reach`; CI installs `rustc-dev` in the two jobs that build the core.

**Closes of the reviews.** Each close has a fixture in `tests/rust_reach_fixtures` that runs a real dispatch with a
counter, and a mutation proof; five controls stay excluded. A `dyn` type argument flows into its instance. A foreign
ADT has an `adt` record: `io::Error` holds its `dyn Error`, and only what is coerced to it. An open `dyn` (an auto
trait, or a trait with a blanket impl) takes each type that flows into foreign code. A `dyn Tr + Send` is keyed by `Tr`.
A type flows into foreign code through a call outside the workspace, and only through a parameter that a clause names
besides its `Sized`. A raw pointer to `()`, `c_void`, an extern type or a number hides a type (a waker, a function
pointer, `Arc::into_raw`): a module or an ADT that holds one reaches the types that a cast hid, and those that foreign
calls took with that ADT in their signature. A `dyn Sub` upcast in a dependency gives its types and async blocks to
its supertraits. A scan without the premise has no facts and says so (UNKNOWN). Facts that name no scan module add a gap.

**Limits.**
- The facts path is a hidden input of the scan: it is not part of the request.
- `not_built` and `test_only` of the reader are listed, not used: a module without facts keeps its pairs, and test facts only add types.
- A value in state of a dependency that `a` never holds is not charged.
- A build script that emits a `--cfg` makes the facts unverifiable (refusal). Build scripts are not read.
- `RUSTC_BOOTSTRAP=1` builds the driver; the code digest does not read its source.
**Tests.** A fake `rustup` tests each `Unavailable` value; `make rustc-facts-e2e` runs the fixtures.
