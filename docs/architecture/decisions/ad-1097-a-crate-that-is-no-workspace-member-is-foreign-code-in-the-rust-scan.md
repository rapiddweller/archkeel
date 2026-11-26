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
