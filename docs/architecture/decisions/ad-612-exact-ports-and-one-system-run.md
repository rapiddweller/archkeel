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

## 2. One system run
AD-522 joined the self-checks of the shell and the core outside the core, in Python. A run of
`archkeel validate --config docs/architecture/architecture-system.json` now checks both in one core.

1. The scan request stays as it is. When its configuration is a system document
   (`"kind": "system"`, `archkeel-system-contract-1`), the core reads it with the safe reader of
   `archkeel-collect` and runs one scan for each part, by the configuration of the part, through the
   one engine path. Each part keeps its profile, collector, contract, namespace and pins. A part
   names no language: its configuration does (AD-522 item 2).
2. The frame of the system holds the rules, details, explained rules, gaps, collection gaps and
   locations of all parts. A rule id that two parts use refuses the run. The new part `system`
   names each part: its id, title, configuration, profile and status, and the ids of its rules.
   The profile of each part is what the Language view of the report reads.
3. The status of the system comes from the status rule of the core (`report::status::run_status`):
   a part that FAILs fails the system; else a part without a result or with UNKNOWN leaves it
   UNKNOWN; else it PASSes. A part that the core cannot run has no result, never a PASS.
4. Rules between the parts (`"rules"` of the document) are refused while the document names one: no
   rule kind reads two replies yet. The topology, the page, the baseline and `--write-baseline` are
   refused for a system run: each is a frame of one part.
5. `make self-validate-system` runs the system, and `tools/self_system.py` is deleted. The join of
   `tools/report_product.py` stays only for the page of the gallery, until the report draws a
   system frame; AD-522 stays the record of that page.

Limits: no relation between the parts is verified (the shell starts the core binary). All parts lie
in one checkout and run with one core, so the commit and core checks of AD-522 hold by construction.
