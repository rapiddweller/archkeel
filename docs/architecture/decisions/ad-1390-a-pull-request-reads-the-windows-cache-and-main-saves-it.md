# AD-1390: A pull request reads the Windows cache and main saves it

Status: accepted. Follows AD-1350 (the facts cache). Issue #2216.

## Why

The Windows type check of a pull request restored and saved a cache under a key with the commit
hash. Each pushed commit saved one entry of about 458 MB. On 2026-11-28 the repository held 9,853 MB in
46 caches, at the limit of 10 GB, and these entries were the largest group. A cache that is evicted is
a cache miss for the base check and the other jobs of the pull requests.

## Decision

1. The job of the pull request restores the cache and never saves it. The key holds `Cargo.lock` and the
   toolchain. The fallback is the newest entry with the same prefix.
2. A new workflow, `windows-cache.yml`, runs on main only when `native/Cargo.lock`,
   `native/rust-toolchain.toml` or the workflow changes (and by hand). It restores or saves the entry
   and runs the same `cargo check --locked --tests`. A pull request reads caches of the default branch.
3. The new key saves one entry for each change of the lock, not for each commit.

The members of `native/` are rebuilt after a checkout anyway, so only the third-party builds in the
entry are used.

## Not done yet

The old entries stay until the repository evicts them. A person can delete the entries of closed pull
requests with `gh cache delete`.
