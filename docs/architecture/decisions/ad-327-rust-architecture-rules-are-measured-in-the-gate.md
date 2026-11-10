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
| Dead `pub` | `unreachable_pub` in each library | none | blocking |
| Crate direction | contract of `native/` (AD-335) | used and declared | blocking |
| Parser crates | `cargo deny` `wrappers` for `tree-sitter*` | collector only | blocking |
| Module cycles | contract of `native/` (AD-335), module level | none | blocking |
| Indexing, arithmetic, `as` casts | `make native-report` | counts | report |

1. A ratchet uses `#[expect(clippy::x, reason = "...")]` on each function over a limit. With
   `-D warnings`, an `expect` that no longer fires is an error. So the list can only shrink.
2. The rules cover production code. One test driver has an `#[expect]` for its complexity.
3. The contract of `native/` names each component and the components it may use. Only a collector
   may use a `tree-sitter*` crate.
4. No module cycle remains (#907). The contract rule `NATIVE-NO-MODULE-CYCLES` fails a new cycle.
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

**Limit.** Indexing, arithmetic and casts are reports, not rules. The `wrappers` entries
name the TypeScript collector; a second collector must be added to them. AD-335 moves the
crate-direction and module-cycle rows to the contract of `native/` when slice 5b-3 lands.

**Checked by** `make native-check`, which runs `make self-validate-native` (AD-335) and
checks the clippy and `cargo deny` rules.

**Note, 2026-11-10 (epic #880, target v2).** `archkeel-snapshot` exists: it owns the POSIX path
text, the contained read, the symlink rule, the 4 MiB limit and the input digests. The TypeScript
rule `installed` (`node_modules`) stays in the TypeScript collector. The contract of
`native/` states the crate directions (AD-335). The reply of the
TypeScript collector is byte-equal on x35 except the code digest, and the binary grew by 0.4 %.

**Note, 2026-11-10 (copies and API).** The clone tool compares windows of 70 tokens. It hides names
and literal values, so a renamed copy still matches. A block of equal rows is skipped when one row
repeats within 24 tokens. A new or grown production clone fails the gate. A clone in a test file only
warns. The API tool counts two numbers for each crate. `items` counts `pub` items and `pub use`
names. `members` counts `pub` fields of `pub` types and enum variants. It does not count what a
macro adds. A number that differs from its baseline fails until the PR sets it.
