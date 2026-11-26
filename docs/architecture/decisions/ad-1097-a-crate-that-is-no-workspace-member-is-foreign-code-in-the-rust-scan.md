# AD-1097 A crate that is no workspace member is foreign code in the Rust scan

**Status.** Accepted. Closes #1989. It extends premise 1 of [AD-1047](ad-1047-rust-dispatch-gaps-use-compiler-type-reach.md): workspace code is a member of `cargo metadata`.

**Reason.** The syntax scan took each `Cargo.toml` below a scan root as a crate of the workspace. A crate that is excluded
from the workspace, or that only a path dependency names, became a module of the scan. With the package name of a member,
the store refused the reply (`duplicate file id`). With another name, the crate was an extra module that a rule could
count as workspace code. The facts side already used the member list.

**Decision.**
1. The core runs `cargo metadata --no-deps --offline` for the manifest at or above each scan root, from a neutral
   directory. It reads the members with the reader of the type-reach producer.
2. The core gives the member directories to the Rust worker in `ARCHKEEL_WORKSPACE_MEMBERS`. The worker starts no process
   (AD-316). The worker removes the files of each package crate that is no member before the scan.
3. A non-member crate with the package name of a member adds a gap. A dependency is read by its package name, so it would
   be read as the member.
4. A scan root with no `Cargo.toml` at or above it adds a gap for each crate below it.
5. When `cargo metadata` does not run, the manifests can still prove a membership: no workspace above the crate, the
   crate holds the workspace, or the workspace names it in `members` (a name or `<directory>/*`) and has no `exclude`.
   Each other crate adds one gap with the reason, and the scan reads every crate as before.

**Not decided here.** A glob other than `<directory>/*`, a path dependency that is a member implicitly, and a crate
that the workspace excludes are decided by `cargo metadata` only.

**Routes back into a member (#2028, #2060, #2105).** A member whose edges pass through code that the scan does not read
gets an edges gap, so indirect rules give UNKNOWN. The evidence is Cargo's, not a text search of source:
1. The resolve graph of `cargo metadata`, run from the real workspace root with its `.cargo/config.toml` (the `--config`
   flags still beat the compiler keys of every config, AD-1130). A path, patched or git source is an edge. A chain from a
   member through a crate that is no member back to a member holds the first member. A workspace member below no scan
   root counts as outside. A git package with the name of a member counts as a copy of it.
2. A local crate outside the members on the way can still read a member (`include!`, `#[path]`, a symlink, `std::fs` in
   a build script or a procedural macro). A build script or a procedural macro holds always. For other crates the
   `rustc` dep-info lists each source file that was read: with `ARCHKEEL_ALLOW_BUILD=1` the core runs `cargo check` of
   those crates (dev and release profile, all targets) and holds the member when a list names a file outside the crate
   or inside a member. A crate with a feature is not proven. The dep-info shows only the configuration that was built:
   a `cfg` on another axis (target, custom flag) can still hide an include (known limit, #2143). Without the
   permission the crate is not proven and holds.
3. Without a lock file, or when Cargo cannot resolve, the core falls back to `cargo metadata --no-deps`: each path, git
   or possibly patched dependency that leads outside the members holds.
An outside crate that is proven to read no member adds no gap. `cargo metadata --locked` never writes a lock file into
the scanned repository.
