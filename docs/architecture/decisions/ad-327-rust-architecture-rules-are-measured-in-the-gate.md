# AD-327 Rust architecture rules are measured in the gate

**Decision.** The Rust workspace in `native/` has measurable rules in `make native-check` and in
one pytest file. A rule either blocks, shrinks (a ratchet) or only reports. This is the first
slice of the Rust architecture plan in epic #880 (R0). Later slices amend this record.

**Problem.** Rust has no `architecture-contract.json`. Only the size of a file (AD-314) and the
ban list of `cargo deny` were checked. A function could grow, a module cycle could appear, and a
panic could end a scan.

| Rule | Tool | Limit | Mode |
|---|---|---|---|
| Function size | clippy `too_many_lines` | 100 lines | ratchet |
| Cognitive complexity | clippy `cognitive_complexity` | 15 | ratchet |
| Nesting | clippy `excessive_nesting` | 4 | ratchet |
| Arguments | clippy `too_many_arguments` | 7 | ratchet (one function) |
| Panic family | clippy `panic`, `unreachable`, `todo`, `unimplemented` | none in production | blocking |
| Overflow | `overflow-checks = true` in the release profile | - | blocking |
| Dead `pub` | `unreachable_pub` in `archkeel-wire` | none | blocking |
| Crate direction | `native/layers.toml` and `tests/test_self_native_layers.py` | declared | blocking |
| Parser crates | `cargo deny` `wrappers` for `tree-sitter*` | collector only | blocking |
| Module cycles | the same test, `crate::` paths | list in `layers.toml` | ratchet |
| Indexing, arithmetic, `as` casts | `make native-report` | counts | report |

1. A ratchet uses `#[expect(clippy::x, reason = "...")]` on each function over a limit. With
   `-D warnings`, an `expect` that no longer fires is an error. So the list can only shrink.
2. The rules cover production code. One test driver has an `#[expect]` for its complexity.
3. `native/layers.toml` names each crate, its role and the crates it may use. A new crate needs an
   entry. Only a collector may use a `tree-sitter*` crate. The vocabulary (component, may use) is
   the one of an Archkeel contract, so a later move to a contract is a change of data.
4. No module cycle remains (#907). `layers.toml` has no `cycles` section. A new cycle fails; a
   crate without a `cycles` section has none.
   The check folds each `#[path]` child into its parent, strips comments and strings, and ignores
   `#[cfg(test)]` modules: a test-only edge is not a production cycle.
5. `overflow-checks` costs 16,560 bytes of binary. On the x35 corpus the median was 1.220 s
   without it and 1.264 s with it (12 interleaved runs, inside the IQR). An overflow of
   `+`, `-` or `*` now stops the scan with `execution_error`. An `as` cast still truncates; the
   count is a report (`cast_possible_truncation`: 4), not a rule.
6. The Python collector will be a second binary with its own crate, profile and code digest.

**Rejected.**
- **A gate on `cargo-modules --acyclic`.** It reports a false cycle between a type and its `new`.
- **Stricter limits (80 lines, complexity 10).** They fire on more functions than a split of
  `imports.rs` can remove now.
- **An Archkeel contract with a Rust reader.** It needs a new language in the product that no
  customer asked for.

**Limit.** This slice does not check clones. The clone check (jscpd or a
stdlib script) is deferred. Indexing, arithmetic and casts are reports, not rules. The `wrappers` entries
name the TypeScript collector; a second collector must be added to them.

**Checked by** `make native-check`, which also runs `tests/test_self_native_layers.py`
(it fails, not skips, when `CI` is set and `cargo` is missing): a bad crate edge, a parser crate in a library,
a crate without an entry, a new or grown cycle and a stale entry all fail on a fixture; the real
workspace passes. `make native-check` checks the clippy and `cargo deny` rules.

**Note, 2026-11-10 (epic #880, target v2).** `archkeel-snapshot` exists: it owns the POSIX path
text, the contained read, the symlink rule, the 4 MiB limit and the input digests. The TypeScript
rule `installed` (`node_modules`) stays in the TypeScript collector. `layers.toml` also declares
the planned crates `archkeel-facts`, `archkeel-store` and `archkeel-build-support` (`planned = true`
until they have code). A collector may use wire, snapshot, facts and build-support; the store may use
facts; no library uses a collector or a parser crate. `native/architecture-contract.json` states
the same directions as a contract, and a test fails when the two files differ. The reply of the
TypeScript collector is byte-equal on x35 except the code digest, and the binary grew by 0.4 %.
