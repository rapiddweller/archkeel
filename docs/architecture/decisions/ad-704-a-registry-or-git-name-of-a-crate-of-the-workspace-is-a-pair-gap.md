# AD-704 A registry or git name of a crate of the workspace is a pair gap

**Status.** Accepted (owner order: fix the false PASS). Part of #880, closes #946. It replaces points 2 and 5 and the open false PASS of AD-502.

**Reason.** AD-502 read a dependency without a `path` (a registry version, `git`) as an external package, so the pair to a crate of the workspace with the same name had no edge. Cargo can still build that crate for it, from inputs the snapshot does not hold or the collector does not follow:
- a `git` URL of this repository;
- a `[patch]` in `$CARGO_HOME/config.toml`, a config above the scan root, or `--config` on the command line;
- a patch, `paths` or source replacement in the repository.

rustc accepts each form, and the edge `app -> base` is real while `NO-APP-TO-BASE` gave PASS. For the in-repository form, AD-502 point 5 turned the rule off for the whole scan. Each name of the workspace then became an edge again, which is a false FAIL when Cargo takes the registry crate.

**Decision.**
1. A dependency with a `path`, or with `workspace = true` and a `path` in `[workspace.dependencies]`, is an edge (AD-502 point 1, unchanged).
2. Any other entry keeps its external import record. When a crate of the workspace with a library or main target has the package name, the collector adds a pair gap from the module of the reference to the module that the same path reaches in that crate. A path through a `use` leaf of the file (`use base_crate::m; m::f()`) is read as for a local crate (AD-604), so its deeper module gets the gap too.
3. The whole-scan redirect predicate goes. `redirects.rs` keeps its other job: a Cargo config, or a manifest above the scan roots, that does not parse is a named gap.

**Why it is sound.** The source of such a name is unknown to the scan in every case: a redirect can be outside the repository. A gap holds each rule of the pair until the contract allows the pair (AD-357). It never gives the edge (no false FAIL) and never removes it (no false PASS).

**Price.** A repository that depends on a registry crate with the name of one of its own crates gets UNKNOWN for that pair until the contract allows it. A patch in the repository that redirects the name gives UNKNOWN where AD-502 gave a true FAIL.

**Rejected.** Reading `[patch]`, `paths` and git URLs to decide the source: the config outside the repository and the command line stay unseen, so the answer would still be a guess.

**Tests.** `tests/test_collector_false_pass_rust_redirect.py`: rustc accepts the git URL of this repository, a patch in `$CARGO_HOME`, a patch on the command line and a patch in the repository, and `app` calls `make` of `base`. The first three are a false PASS on main `ed9d2636d`. The two twins without a readable redirect are UNKNOWN, where main gave PASS or a false FAIL. `tests/test_collector_false_pass_rust_layout.py` (each AD-502 form is UNKNOWN now), `redirects_tests.rs`.
