# AD-316 Native collectors live in native/ and reply with protocol 8

**Decision.** Rust code lives in `native/`, a Cargo workspace with its own `Cargo.toml`,
`Cargo.lock` and `rust-toolchain.toml`. A root `Cargo.toml` would be a stray root file. The
workspace has two crates:

- `archkeel-wire` decodes the request and encodes the compressed reply. It also owns
  `stable_id`, `module_identity` and `source_digest`. Each one gives the same text as its Python
  twin.
- `archkeel-typescript-collector` is a binary. The host starts it like any collector from
  `[scan].collector_argv`. The process port, timeout, output limit, Windows job object and the
  `decode_response` trust boundary do not change. There is no PyO3 extension.

PR 4.1 of issue #880 has two parts. PR 4.1a (this decision) adds the crates and the host
acceptance tests. PR 4.1b adds the wheel hook (AD-317), the CI jobs, the macOS job and the
dependency policy of `cargo deny`. The binary is a drop-in for the Python TypeScript collector:

1. It reports the same profile and adapter name, `archkeel-typescript-imports`, and its own
   runtime: `rust`, the compiler version, and `>=1.88`.
2. It declares the registered import capability: the sections `imports` and `unknowns` and the
   features `literal-imports`, `relative-specifiers`, `node-builtins` and `local-runtime-closure`.
3. One function chooses the reply version. A 3.0.0 or 8.0.0 request gets the compressed 8.0.0
   reply. A 9.0.0 request gets a 9.0.0 reply, which has the same shape (AD-313).
4. It selects files as `config.load_config` does: `extends`, `files`, `include`, `exclude`,
   `allowJs`, `checkJs`, `outDir` and `declarationDir`. It reports the files, inputs, coverage
   and file evidence. A directory, an entry or a file name that it cannot read is a collection gap.
5. The skeleton extracted no imports and gave each file one `source_resolution_gap`. AD-320
   replaces this with the import records. The collector invents no evidence.
6. A 9.0.0 request with `exclude_test_sources` removes test sources with the rule of
   `profiles.is_test_source` (AD-313). When this removes every file, the gap "No production
   source files in scope after the test exclusion" keeps the scan incomplete.

Rust code is outside the architecture contract and `tests/test_self.py`, because the self-scan
reads Python only. Crate boundaries and `cargo clippy -D warnings` keep the Rust modules apart.
Each crate forbids `unsafe` code. Each `.rs` file has at most 500 lines (AD-314), and unit tests
are in sibling `*_tests.rs` files. The license header test covers `.rs` files.

`native/deny.toml` is the dependency policy for the six wheel targets. It fails on each RustSec
advisory, a license other than MIT or Apache-2.0, a source other than crates.io, a wildcard
version, and a network, TLS or process crate. `make native-check` runs `cargo deny` with the
pinned version. The PR gate job `Native` runs it on Linux; macOS and Windows run in Full only.

**Reason.** The host already validates this wire. A drift in the native reply fails closed as
`protocol_error`. The Python collector stays the exact difference oracle until it is deleted, and
only one producer changes when protocol 10 gets one fact record. Protocol 9 belongs to AD-313.

**Rejected.**
- A PyO3 extension. The binary reads untrusted source. In the host process, an allocation failure
  or a stack overflow aborts the host. PyO3 turns only a panic into `PanicException`, and that is
  a `BaseException`. The timeout, the output limit and the process group apply only to a process.
  The process contract exists and has tests. ABI coupling is not a reason: an `abi3` wheel serves
  CPython 3.11 and later, and only the free-threaded 3.14t needs its own wheel.
- A new fact stream first. Two producers would change, and PR 4 would wait for its design.
- Code from codebase-memory-mcp now. The skeleton has no resolver that needs it (YAGNI).

**Limit.**
- AD-320 reads the compiler options, the script environment and the `package.json` files.
- Without `ARCHKEEL_VERSION` at build time, the adapter version is `0+unknown`.
- Timings are not a performance claim. The bans list known crates; a new crate with the same
  purpose needs a review of its own.

**Check.** `tests/test_collector_native_typescript.py` runs the host report.
It decodes 3.0.0 and 8.0.0 replies with consistent coverage. It compares files, file evidence and
inputs with the Python collector on four fixtures. It checks `missing_tool`, `execution_error`,
`timeout`, the output limit and the 9.0.0 test exclusion. The `cargo test` expected values come
from the Python functions. `make native-check` runs format, lint, `cargo deny`, tests and build.
`tests/test_native_ci.py` checks the pinned `cargo deny` and the PR gate job.

**Note (2026-11-09, issue #880).** `ARCHKEEL_CODE_DIGEST` covers each `.rs` and `Cargo.toml` outside
`target/`. A new crate or directory changes it; `test_collector_native_digest.py` checks this.
