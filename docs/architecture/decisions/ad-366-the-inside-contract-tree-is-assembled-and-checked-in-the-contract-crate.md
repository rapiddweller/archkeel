# AD-366 The inside-contract tree is assembled and checked in the contract crate

**Status.** Accepted. Epic #880, M6b contract lane 1. It extends [AD-364](ad-364-the-rust-contract-parser-reads-the-whole-grammar.md).

**Decision.**
1. `archkeel-contract` has the module `policy`. Its entry `assemble_tree(root_path, root,
   insides)` takes the result of `parse` for the root and `(reference, identity, bytes)` for each
   inside contract. It is the only way from `ParsedContract::NeedsTree` to a usable
   contract; a doctest that must not compile checks this. The crate reads no file and uses no
   workspace crate.
2. It makes each check of `load_inside_contract_tree` (`ir/codec_inside.py`) in the Python order:
   a parent key that is a root label or the key of another mount, an unsafe reference, a path
   without bytes, a cycle, a duplicate mount, an invalid inside contract (with its parse kind),
   root-only declarations in an inside, a scoped ID that the tree holds, and one module target
   path in two contracts. Each problem is one `TreeIssue`, with the pointer, parent key, path and
   reason of Python.
3. The result is one `Result`: the whole `ContractTree` or a `TreeError`. A tree with an issue is
   never returned.
4. The tree holds the scoped mounts, the provenance paths, the digest of the bytes and the
   comparison digest that an amendment binds. Both digests are equal to Python.
5. The duty of the shell: it resolves each path, refuses a path outside the repository, and sends
   the resolved repository-relative path as the identity, never an empty one. The crate refuses an
   inside whose identity differs from its normalized reference (`Linked`).
6. The walk uses an explicit stack, not recursion. A mount deeper than 900 levels is `TooDeep`
   (lead decision L-24, the bound of the Dart collector); the walk takes time linear in the mounts.
7. `TreeIssue::kind` serializes with a stable name (`IssueKind::word`). When each issue is
   `Missing`, `TreeError::missing_paths` gives the paths that the shell must read; it then calls
   the entry again, in rounds.

**Reason.** The comparison digest binds every amendment, and the mounts decide the scope of each
rule. A shell that assembles the tree must hold the Python contract model. The owner decision of
2026-11-11 puts `validate` in the core before Cut A, and `--against` needs this tree.

**Rejected.**
- The shell assembles the tree and sends it. It needs the contract model in Python.
- The core reads the files. The core has no file access (owner decision).
- Return the issues next to a partial tree, as Python does. A caller could use a partial tree.

**Limit.** Rust is stricter than Python in six cases: bytes that no mount reads (`Unmounted`); two
inputs with one path (`Duplicate`); an input path or identity that is not a repository path
(`Unsafe`); a JSON key two times (AD-364); a mount deeper than 900 levels (`TooDeep`; Python
stops near 984 with a `RecursionError` and no verdict); a symbolic link (`Linked`; Python refuses a
link to a mounted file as a duplicate mount and accepts a link to an unmounted file). Python writes no comparison bytes when the root
version cannot hold a rule of an inside; Rust writes them, and the digests stay equal. The
contract checks against the code (`check/validation/inside.py`) are not here. No command calls
the entry yet. `docs/known-limits.md` lists the stricter cases.

**Tests.** `tests/test_rust_contract_tree_parity.py` with `tests/rust_contract_tree_cases.py`
(each repository tree with mounts, hostile trees and generated trees);
`native/contract/src/policy/tree_tests.rs`, one test for each check.
