# AD-436 A platform wheel carries the core and no other wheel is built

**Status.** Accepted. Part of #880. It changes points 2, 3, 5, 8 and 9 of AD-317 and replaces the
first limit of AD-432. The lookup and the refusals of AD-432 do not change.

**Decision.**
1. A wheel of `archkeel` carries one binary, `archkeel/_native/archkeel-core` (`.exe` on Windows),
   and the file `<binary>.sha256` with the SHA-256 of that binary. The two collector binaries are
   not in the wheel: the core links both collectors (AD-406).
2. The hook `native/hatch_build.py` refuses a wheel build without `ARCHKEEL_BUNDLE_NATIVE`.
   `1` runs `cargo auditable build --release --locked -p archkeel-core` and adds the CycloneDX SBOM
   of the core. An absolute path bundles a prebuilt core. An editable install bundles nothing.
   So no pure wheel exists, and `make build` builds only the sdist.
3. The sdist does not carry `native/` and does not run cargo. A build from the sdist refuses and
   gives the remedy: install a platform wheel, or give a prebuilt core in the variable.
4. The six targets of AD-317 do not change. Each wheel is built on its own target.
5. The installed shell runs only the binary of its own package, and only when the digest file is
   equal to the SHA-256 of the binary. A missing binary or digest is `core_binary_not_found`.
   A wrong digest and a binary that cannot start are `core_error`. Each is exit 2, never a verdict.
   The build output of a checkout is used only when the package is below `src/` of a directory
   with `pyproject.toml` and `native/core/Cargo.toml`. An installed package never uses it.
6. `make native-wheel` builds the wheel, checks its tag, content and SBOM, and installs it alone in
   a new environment outside the checkout. The installed `archkeel validate` must give the result
   of the core of the checkout: PASS and FAIL for a Rust project, UNKNOWN for a TypeScript project.
7. `tools/release_core.py` is the release guard. It refuses a wheel without the binary, a wheel
   whose digest is for other bytes, and a wheel of a platform in `NO_VERDICT`. Then it installs the
   wheel of the build host alone and requires a verdict of the bundled core.
   `tools/publish_release.py` accepts exactly the sdist and the six platform wheels.
8. `NO_VERDICT` holds `win_amd64`. The core requires the canonical text of each root, and Rust
   gives the canonical path of Windows with the prefix `\\?\`, so the core refuses each root.
   `PUBLISH_NATIVE_WHEELS` is `"true"` only when `NO_VERDICT` is empty. It stays `"false"`, and the
   first job of `release.yml` names the platform.

**Reason.** The shell decides nothing (AD-432). A package without the core can only refuse, so
such a package must not be built. A refusal at build time names the remedy once; a pure wheel
would install on each platform and refuse each run. One binary has one digest and one SBOM.

Measured on macOS arm64: the wheel grows from 3,400,053 bytes (two collectors) to 4,397,661 bytes.
The core is 9,300,528 bytes. The installed `validate` takes 0.1 to 0.3 seconds for a fixture.

**Rejected.**
- cargo in a build from the sdist. The sdist must then carry `native/`, the install must download
  each crate, and an install without Rust fails later with a longer error.
- A pure wheel as the default. An installer selects it for each platform without a wheel.
- A release of five platforms beside a Windows wheel that refuses each run.
- To remove Windows from the matrix here. The published platforms are a product decision.
- A check of the executable bit in the lookup. The start of the binary already gives `core_error`.

**Limits.**
- The digest finds a damaged file and a wrong file. It does not stop a party that can write the
  binary and the digest file. The binary can also change between the check and its start.
- Windows gave no verdict when this decision was made. AD-442 corrected `native/collect`, so the
  core decides on Windows now, and the installed-wheel test requires the result of the checkout core
  on each platform. The guard of point 8 still lists `win_amd64`; a later change lifts it. The
  release opens when the guard is lifted or when the owner removes Windows from the matrix.
- An install from the Git URL needs `ARCHKEEL_BUNDLE_NATIVE=1`, cargo and `cargo-auditable`.
- A platform outside the matrix has no wheel, and its build from the sdist refuses.
- The core starts Git only at `/usr/bin/git` on Linux and macOS. The pypa images have Git in
  `/usr/local/bin`, so the Linux wheel jobs add a link.
- The wheel jobs run in Full verification, not on a pull request (AD-348).

**Way back.** `git revert` of the squash commit restores the collector wheels and the pure wheel.
No release from this line exists, so no published package changes.

**Tests.** `tests/test_cli_installed_wheel.py` installs the wheel alone and checks the verdicts,
each refusal and that a binary in the project, the current directory, `PATH` or a build output
beside the environment never runs.
`tests/test_collector_native_wheel.py` checks the hook, the refusal of a build without the core
and the content of the built wheel. `tests/test_native_ci.py` checks the guard, the flag rule and
`tools/release_core.py`. `tests/test_publish_release.py` checks the set of release assets.
