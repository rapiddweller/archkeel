# AD-317 A platform wheel carries the native TypeScript collector

**Decision.** The distribution `archkeel` can ship the binary of AD-316 in a platform wheel.

1. `native/hatch_build.py` is a hatch build hook of the wheel target. It keeps hatchling,
   `hatch-vcs` and the readme hook. maturin is not used.
2. The hook acts only when `ARCHKEEL_BUNDLE_NATIVE` is set. The value is the absolute path of a
   prebuilt binary, or `1`. With `1`, the hook runs `cargo auditable build --release --locked` in
   `native/` and sets `ARCHKEEL_VERSION` to the wheel version. An editable install ignores it.
3. The hook sets the tag `py3-none-<platform>` and `Root-Is-Purelib: false`. The binary is package
   data: `archkeel/_native/archkeel-typescript-collector`, with `.exe` on Windows and mode 0755.
4. `host_platform` takes the first supported tag of `packaging.tags.platform_tags()`. It skips
   the generic `linux_<arch>`, which packaging 26 yields first. `wheel_tag` maps it:

| Target | Wheel platform tag |
|---|---|
| macOS x86_64 | `macosx_10_12_x86_64` |
| macOS arm64 | `macosx_11_0_arm64` |
| Linux glibc x86_64, aarch64 | `manylinux_<host glibc>_<arch>` |
| Linux musl x86_64 | `musllinux_<host musl>_x86_64` |
| Windows x86_64 | `win_amd64` |

   The macOS versions are the default deployment targets of Rust. The hook sets
   `MACOSX_DEPLOYMENT_TARGET` to them for its cargo build. Each other platform is an error.
5. The sdist ships the hook but not `native/`. An sdist, an editable install and a default wheel
   never run cargo. The default wheel is byte-equal to a build without the hook.
6. The host does not use a bundled binary yet. The default TypeScript collector stays the
   Python collector. PR 4.4 adds the lookup with `importlib.resources` and switches the default.
7. The release profile has `strip`, `lto = true`, `codegen-units = 1` and `panic = "abort"`.
8. With `1`, the binary lists its crates for `cargo audit bin`, and the hook adds a CycloneDX 1.6
   SBOM as `.dist-info/sboms/archkeel-typescript-collector.cdx.json` (PEP 770). It lists each
   linked crate with license, package URL and SHA-256, and has no time and no local path.
9. Full verification runs `make native-wheel` on each target: manylinux 2014 and musllinux 1.2
   images pinned by digest, macOS 15 and Windows 2025. Each job checks the tag and the SBOM,
   installs the wheel and runs the binary. `tools/publish_release.py` accepts the pure wheel,
   the sdist and none or all six platform wheels. The release copies the platform wheels into
   `dist/` after Full passes (AD-476 removed the flag `PUBLISH_NATIVE_WHEELS`).

**Reason.** Tools that read untrusted code, for example ruff, uv, ty and pyrefly, ship a Rust
binary in platform wheels and start it as a subprocess. The binary has no Python ABI, so one wheel
for each platform serves Python 3.11 and later. One distribution has one version, so the host and
the binary cannot drift apart. A panic that aborts gives a nonzero exit, and the host reports
`execution_error` (`Collector exited -6`). No code uses `catch_unwind`.

Measured on macOS arm64, Rust 1.88: the release binary was 879 728 bytes, 740 464 bytes with
`strip` only. The profile gives 567 520 bytes (617 328 bytes with unwind). A clean build takes
6.9 s against 2.6 s. `lto = "thin"` gives 602 656 bytes in 5.4 s, so fat LTO stays.

**Rejected.**
- maturin. It replaces the build backend, the VCS version and the readme hook for one file.
- A second distribution for the binary. Two versions must then match exactly.
- `infer_tag`. It gives a tag for each CPython version, and the binary does not need that.
- A command in `scripts/`, as ruff does. The host needs a path, not a command on `PATH`.
- cargo at install time. An install without Rust must not fail.
- `cargo-cyclonedx`: one more tool on six targets for one JSON file.
- A repository variable as the release gate: its change is not reviewed and not tested.

**Limit.**
- The tag follows the build host. A cross build gets a wrong tag. Build each wheel on its target.
- The glibc version of the build host is the minimum. Build on a manylinux 2014 image for 2.17.
- No wheel with a binary is published before PR 4.4, which sets the gate to `"true"`. The
  binary has no script globals and no named bindings yet (AD-320).
- A prebuilt binary gets no SBOM: the hook cannot know its crates.
- `missing_tool` for TypeScript without the binary starts when the Python collector is deleted.

**Check.** `tests/test_collector_native_wheel.py` tests the tags of the six targets, the selection
from the tag lists of real hosts, the error for other platforms and the SBOM. It compares the
default wheel with a build without hooks. Its `native_wheel` test checks the tag, the mode, the
SBOM and the `.dep-v0` section, installs the wheel, finds the binary with `importlib.resources`
and runs it. `tests/test_publish_release.py` and `tests/test_native_ci.py` test the gate.
