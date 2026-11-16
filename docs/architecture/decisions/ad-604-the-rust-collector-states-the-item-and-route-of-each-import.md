# AD-604: The Rust collector states the item and the route of each import

Status: accepted (owner order). Part of #880. It extends AD-428, AD-500 and AD-504 to Rust.

## Context
The Rust collector stated no profile limits and wrote no symbol on a path into another crate. So
`interface_boundary`, and a `public` entry `module:Name`, held every rule of a Rust run. AD-588
measured it on `native/`: 85 `scope_proof` gaps, and a planted use of a private name gave no FAIL.

## Decision
1. Each import record into the workspace names what it imports (`symbols_known: true`):
   - an item: the segment after the deepest module that the path names (`dep::m::T::f` names `T`);
   - a member of an inherent `impl` block (#953): the type of the block, in the module of the block;
   - a glob: `*`, which names no known name (the gap "unread import binding");
   - a whole module (a `use` of a module, a manifest dependency): no symbol.
2. `reexport_chain` is the publication route of the item: `module.name` hops from the module that
   the path names, through each `pub use` leaf, to the definition (`routes.rs`). Each hop is true:
   the path, or the leaf before it, names that name there, and rustc resolved it. A step is taken
   by the rules of AD-544: no attribute can swap the file, the file declares the name once, no
   macro call in item place can add one, and the name is a definition or the one module-level leaf
   that binds it. A definition, or a leaf into a crate outside the workspace, ends the route.
3. A route that stops before its end (a glob or a macro may give the name, a leaf that names a
   module) keeps its true hops and states `route_complete: false`, a new optional fact. The model
   passes the import when a hop is public and keeps the gap "unproven publication route" when no
   hop is public, because a later hop may be public. An absent value means a complete route, as
   the TypeScript and Python collectors write. An item of an inline module has no route.
4. A path through a `use` leaf into another workspace crate (`use dep::m; m::f()`) gets a record of
   its own. Before, it had none, and the leaf carried the edge.
5. The linked reply states `dependency_symbols` and `interface_boundary` as `Supported`, with the
   feature `rust-item-routes-v1`. The store refuses a Rust statement without the feature. The
   subprocess reply keeps its frozen statements, as the Python survey does (AD-504).
6. `Profile::namespace_uses_recorded` is true for Rust: a module is no value, so each use through
   it is a qualified path, and each qualified path ends as a record or a gap (AD-352, item 4). The
   interface rule judges those uses and does not judge the import of the whole module. A
   TypeScript namespace object and a Python module object are values, so their import stays judged.

`model`, `eval`, `core` and `report` name no language: they read the facts and the profile trait.

## What stays UNKNOWN (never PASS)
- a glob into another component; a name that a macro may publish further, unless a hop is public;
- a method call whose receiver the scan does not know: the pair gap of #953 holds the rule;
- a path that the resolver cannot place: its collection gap holds the rule.

## Limits
- A procedural macro (a derive or an attribute) is not read. If it adds a `use` of a defined name in
  another namespace, the route misses that hop. That can only give a FAIL where the truth is PASS.
- The model takes a name with a leading `_` as private (a Python rule, AD-504). For Rust that can
  only give a FAIL.
- The subprocess reply of the collector has no statement, so a run through it keeps AD-500.

## Tests
`tests/test_cli_native_rust_interface.py`: 13 plants that rustc accepts (`cargo check`): a public
name, a private name, a re-export, a deep path, a module binding and a use through it, a crate
alias, a glob, a macro item with and without a public hop, a method of an unknown receiver, and a
member of a type in the module of its block. Unit tests: the route of a re-export chain, of a macro
item and of a glob (`module_edges_tests`), and the statement of the store (`registered_tests`).
