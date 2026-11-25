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
associated-type ADTs of reached impls (any type reaches a blanket impl). For each `dyn Tr` in reach, add each type that is coerced to `Tr`.

**Premises of a PASS (`rust_type_reach`).** This list is the one place of the premises. The contract declares the
premise `rust_type_reach`, and each PASS that a dropped gap decides names it.
1. Whole program. The scanned Cargo workspace is the whole program. No code outside the Rust build (C, assembly,
   `dlopen`, a plug-in) runs an impl of the workspace. Workspace code is a crate that ran under the driver as a member
   of `cargo metadata`. Any other crate is foreign. The verifier refuses facts that name a non-member file. A library
   `pub fn` that only a downstream crate calls loses its generic instances: a library is not a whole program. State
   that a dependency holds for the workspace (`#[global_allocator]`, `log::set_logger`) is not charged.
2. This target, this profile and this matrix. Only the dev profile is built: `#[cfg(not(debug_assertions))]` code is not
   seen. The matrix is default, no default features, all features and each feature alone: a cfg set such as
   `all(feature = "a", feature = "b", not(feature = "c"))` is never built when `c` is default. Another target is not
   seen. More than 16 features give no facts (`TooManyFeatures`). A PASS does not speak about that code.
3. The repository is trusted. `cargo check` runs its build scripts and proc macros, and `--offline` does not stop their network access.
4. The driver and the compiler are bound. The pinned rustc (`tools/rustc-facts/rust-toolchain.toml`) gives the
   same types as the toolchain of the project. The facts bind the `rustc -vV` text, the driver hash, the
   configuration, the `Cargo.lock` hash and the SHA-256 of each source file that rustc read. The collector checks each
   binding. A mismatch gives no facts, and the gaps stay.
5. Unsafe raw-pointer code is charged with the worst case. A module, or an ADT of any crate, that holds a raw pointer
   to `()`, `c_void`, an extern type or a number reaches each type that a cast or a transmute hid, and each type that
   calls outside the workspace took with that ADT. A round trip through an integer address (`ptr as usize`) is not
   seen, and a PASS does not speak about it.

**Stage 1.** `tools/rustc-facts` is the driver: a binary crate with no dependency, its own toolchain file and
`Cargo.lock`. It hooks `mir_built`. `native/collect` (`FactsTools::produce`) builds it and runs `cargo check --workspace
--all-targets --offline --locked` for each configuration. `native/rust` (`Expected`) needs one file for each unit that
Cargo names, and each scanned file with its hash. `native/facts` holds the typed cause `Unavailable`.

**Rejected.** SCIP (AD-1036): no temporaries, drops or coercions. Syntax-only reach: no inferred type. The driver in
`native/rustc-facts`: `extern crate rustc_driver` made the self-scan UNKNOWN.

**Stages 3 and 4.** `[scan] rust_type_reach = true` (Rust only) makes the core run `FactsTools::produce` and pass a
descriptor path to the Rust worker. `Filter` drops a trait-impl, destructor or receiver gap when no config can run an
impl of `b` from `a`. A `dyn Tr` counts as every implementer of `Tr`. A pair without facts for `a` stays. Any
`Unavailable` cause adds one whole-scope gap with the exact reason (UNKNOWN). Contract 3.22.0 adds the premise.

**CI.** The driver links `librustc_driver` and `libLLVM`, so it needs `rustc-dev` and `llvm-tools` (about 160 MB
compressed). Without `llvm-tools` the link fails and the collector says only "the rustc driver did not build". The
toolchain file of the core does not list them, and the six wheel jobs do not install them. `make type-reach-setup`
installs them from `tools/rustc-facts/rust-toolchain.toml`, then runs `cargo fetch --locked` in `native/`, because the
producer runs `cargo check --offline` over the workspace. Each job that runs the self-check calls it once before any
parallel step, and so does `publish-gallery` of `pages.yml`. `tests/test_native_ci_type_reach.py` fails when a job does
not. A test that needs the facts skips without them and fails in CI (`tests/rustc_dev_support.py`, AD-1048).

**Closes of the reviews.** Each close has a fixture in `tests/rust_reach_fixtures` that runs a real dispatch with a
counter, and a mutation proof. A `dyn` type argument flows into its instance. A foreign ADT has an `adt` record. An open
`dyn` takes each type that flows into foreign code. A raw pointer to `()`, `c_void`, an extern type or a number hides a
type: a module or an ADT that holds one reaches the types that a cast hid. An opaque type or an async block in a type
argument flows by its name, and so do the `dyn` traits of an associated type. Facts that name no scan module add a gap.
A warm cache keeps the crate ids of fresh members. AD-1112 bounds the work cache.

**Limits.**
- The facts path is a hidden input of the scan: it is not part of the request.
- `not_built` and `test_only` of the reader are listed, not used. A module without facts keeps its pairs.
- A build script that emits a `--cfg` makes the facts unverifiable (refusal). `RUSTC_BOOTSTRAP=1` builds the driver.
**Tests.** A fake `rustup` tests each `Unavailable` value; `make rustc-facts-e2e` runs the fixtures.
