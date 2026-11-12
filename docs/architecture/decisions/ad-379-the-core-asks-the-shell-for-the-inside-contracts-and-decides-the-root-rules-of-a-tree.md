# AD-379 The core asks the shell for the inside contracts and decides the root rules of a tree

**Status.** Accepted. Epic #880, WP6 contract lane. It wires [AD-366](ad-366-the-inside-contract-tree-is-assembled-and-checked-in-the-contract-crate.md) into the core of [AD-370](ad-370-the-core-decides-the-rule-kinds-of-modules-and-ownership.md).

**Decision.**
1. The `Contract` request of the core carries the root path, the root bytes and the inside files
   that the shell read: `(reference, identity, bytes)`. The core reads no file.
2. A root that mounts inside contracts answers `Missing(paths)` (`TreeError::missing_paths`)
   until the shell sends each path. The shell reads them with the duties of AD-366 (resolved
   identity, inside the repository) and sends the request again with every file. Each round
   assembles the tree again from the whole input, so a file that changes between rounds gives
   the tree of the last bytes or a named error.
3. A tree with any issue is refused by name (`refused: inside-contract tree: ...`). A refused or
   missing tree gives no rule and no model; the frame names it and exits 3.
4. Bounds: at most 1 024 inside files and 64 MiB of inside bytes in one request, inclusive,
   checked in `contract::answer` before any parse. A breach is a named refusal of the contract
   (exit 3); the dual run has read the request already, so it has no second check. The shell has
   the same bounds and at most 901 rounds (the depth bound of 900 and a last round).
5. After assembly the model is the model of the root contract. The core decides the root rules as
   S1 to S4 do. Each rule of a mount is named (`Unsupported::InsideRule`): the clipped scope of a
   mount (`_inside_source_domain`) is not in the core. A root with mounts is never a complete
   scope: the proof notes `Part::MountedTree` (`model/src/proof.rs`), so `Scope::complete` and
   `Scope::run` name it and no PASS path can skip it. The `TreeScope` arm before the PASS arm of
   `core/src/rules.rs` is the second line. The run status of a tree is never PASS.
6. One UML target names the tree when any contract of the tree has `declarations.uml`, as
   `check/uml.py` does.
7. Protocol change of AD-360 point 7: `archkeel-dual-run-3` adds `insides`, a list of
   `{reference, identity, hex}`. A frame that needs files has `self_test.contract.missing`.
   The harness (`tools/dual_run_tree.py`) is the shell of the dual run.
8. The later slice that decides inside rules must add, for each scoped contract, what Python
   adds in `evaluate.py:321`: the clipped source domain and its failures (`:728`), the inside
   limits (`crate_scope.py:143`), the dynamic limits (`dynamic_dependency_limits`), the subject
   check of each scoped rule, and `named`, `limits` and `rule_failures` of `proof.rs`, which read
   only the root `contract.rules()` today. Only then can `Part::MountedTree` go.

**Reason.** 248 of 2 298 differences of the S1 to S3 run named the missing tree, and 298 cases
had no usable contract. A root rule reads the modules and owners of the root contract, so its
violations, and thus its FAIL, do not depend on the mounts. Its other verdicts do: Python reads
the mounts, and a failure of a mount (an inside claim outside its parent) makes root
`complete_assignment`, `root_layout` and both external rules UNKNOWN where they pass without it
(`tree/an-inside-claim-outside-its-parent-makes-passing-root-rules-unknown`). So a root rule of a
tree gives FAIL or a named gap, never PASS (point 5).

**Rejected.**
- The core reads the inside files. The core has no file access (AD-359).
- Decide the inside rules now. The clipped scope and its coverage records belong to the decision
  path of slice S4; a guessed scope can give a false FAIL.
- Use the valid mounts of a tree with issues, as Python does. A partial tree is a silent subset.
- A session that keeps the files of earlier rounds. One request holds the whole input, so no
  state can mix two versions of a file.

**Limit.** Stricter than Python, each a named gap: a tree with an issue (Python evaluates the root
and the valid mounts; 4 corpus cases and 3 `tree/*` cases); more than 1 024 files or 64 MiB; the
six cases of AD-366; each inside rule; each root rule of a tree that Python can PASS (42 rules of
the `tree/*` cases). The store refuses the
Python and Dart replies, so 288 of the 293 tree cases of the corpus still name the reply.

**Tests.** `native/core/src/contract_tests.rs` (rounds, wrong identity, duplicate reference, a
file not asked for, a file missing after it was asked, changed bytes, a cycle, depth 900 and 901,
3 000 mounts, more than 64 MiB); `native/core/src/tree_tests.rs` (one mount, the second line, the
status); `native/core/src/dual_run_tests.rs`;
`tests/test_dual_run_shell.py` (the loop and its bounds at the boundary, a chain of 900 rounds, a link, a path outside);
`tests/test_native_core.py` (`test_the_tree_cases_equal_python_on_the_decided_kinds_or_name_each_gap`,
`test_the_run_status_of_a_tree_is_never_pass`).
