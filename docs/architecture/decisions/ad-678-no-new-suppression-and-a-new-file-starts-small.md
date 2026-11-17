# AD-678 No new suppression, and a new production file starts at 400 lines at most

**Status.** Accepted. Owner decision of 2026-11-16. Part of #880. It follows AD-314 (500 lines) and the honesty rule.

**Reason.** Agents squeezed files to 499 lines and hid dead code behind `allow(dead_code)`: 22 `allow` attributes of production Rust exist, 18 of them `cfg_attr(not(feature = "dump"), allow(dead_code))`.

**Decision.**
1. `tests/test_born_small.py`: a production file that the branch adds (`git diff --diff-filter=A origin/main...HEAD`: `src`, `native`, `tools`, not `*_tests.rs`, not `tests/`) has at most 400 lines. Existing files keep the limit of 500.
2. The same file: each `#[allow(...)]`, `#![allow(...)]` and `cfg_attr(..., allow(...))` in production Rust equals an entry of `native/suppressions.json` with a reason. A new attribute fails. An entry whose attribute is gone fails, so the list only shrinks. The 22 entries are known debt, visible and reviewed; they are not accepted design.
3. `make native-check` runs clippy with the default features, with `--no-default-features` and with `--features dump,harness`, so an item that only a feature uses shows as dead in a plain build.

**Rejected.** `clippy::allow_attributes = "deny"` at once: it breaks the build until the 22 sites are fixed; the list makes the debt a ratchet now.

**Tests.** `tests/test_born_small.py`.
