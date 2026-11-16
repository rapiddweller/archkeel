# AD-612: Exact ports, and one system run

Status: accepted (owner order). Part of #880. It amends AD-588.

## 1. Exact ports
A module port is a prefix (`port_judged`). The root port `native.archkeel_facts` of a requirement
therefore permitted each module of the crate, and AD-608 had put such root ports on three
requirements. 129 requirements had a crate root as a port.

Decision: a use of a name at a crate root is a symbol port `root:Name`, and a use of a deeper module
is a module port of that module. The Rust collector names the item of each import (AD-604), so a
symbol port is decided. 79 requirements now have exact ports. A new use of another root name fails
`NATIVE-REQUIRES-COMPLETE` (probe: `archkeel_facts::Section` in `model-terms`).

50 requirements keep the root port. Their component holds the manifest of its crate, and a
dependency in `Cargo.toml` names the whole crate, with no symbol. The contract language has no exact
module port, so the root port is the only true statement of that edge. A component that holds a
manifest and uses names of the same crate keeps the coarse port for those uses too; the symbol list
of `public` (AD-604, AD-608) stays the precise guard of them.

`tests/test_native_contract_rules.py` holds the shape: no requirement lists a root port and symbol
ports of the same root.
