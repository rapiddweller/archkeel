# AD-350 The native self-check runs the bundled build of the tree

**Decision.** `make self-validate-native` checks the Rust workspace `native/` with the collector
that a platform wheel bundles, not with a configured collector. Since
[AD-344](ad-344-only-a-producer-that-the-host-trusts-can-give-pass.md) a `collector_argv` is an
external producer and gives at most UNKNOWN, so the self-check could not give PASS when
`native/archkeel.toml` named the debug build.

1. `native/archkeel.toml` names no collector.
2. `make self-validate-native` builds the collector of the same source tree with the installed
   package version stamped in, as the wheel build does, and copies it to `src/archkeel/_native/`,
   where the host looks for the bundled binary.
3. It runs the check and then removes only the copied file.

**Why.** The build of this tree is exactly what a wheel carries, so the self-check proves the
bundled producer. The host is unchanged, and a customer `collector_argv` is still external.

**Check.** A test guards that `native/archkeel.toml` names no collector. The test that a
customer `collector_argv` gives UNKNOWN stays.

**Limit.** A stop between the copy and the removal leaves the binary in the source tree; it then
shows as an untracked file.
