# AD-664 A contract can declare the reach of a door site

**Status.** Accepted (owner decision 2026-11-16). Part of #880, refs #723. It amends the strict
owner decision of AD-564: without a declaration nothing changes.

**Reason.** A door (`eval`, `exec`, `compile` of a text, an unpickler, a loader with an unknown
name, `__import__`, a TypeScript call through a run-time key) can run code that the scan cannot
see. Its gap states `every_module`. Many doors are bounded by design, but syntax does not prove it.

**Decision.**
1. The collector marks a door gap with `GapData.door`: the form, the line, the scope (dotted
   class and function names) and, for an import statement, the name that it binds. Only the
   forms of the owner list get a door. A door module, a pickler, a door string and the import
   state get none, so no declaration can apply to them.
2. Contract 3.15.0 adds `declarations.door_reach`. One record names one site (`module`, `door`,
   and `line` or `scope` or both), the prefixes that the door may import (`loads`) and the
   prefixes whose names it may change (`changes`). The root contract declares; a declaration of
   an inside contract is the defect `door_reach.inside`.
3. The model (`door_reach.rs`) applies a declaration only when it matches exactly one door, the
   door has no other declaration, each `changes` prefix holds a module of the scan, each `loads`
   prefix holds a module of the scan or lies outside its top packages, no other module imports
   the bound name of the door, and the door gap covers no unresolved import. Else the
   declaration is a defect row (`door_reach.unmatched`, `.ambiguous`, `.repeated`, `.invalid`)
   with exit 2, and the door keeps `every_module`. A door that moves or changes its form no
   longer matches, so its declaration becomes `unmatched`.
4. An applied declaration replaces the effect of the gap by `modules` of each module below a
   `changes` prefix, or by no effect. The door writes a declared import from its module to each
   module below a `loads` prefix, or to the outside package of the prefix. The edge rules, the
   cycles and the receipts read it as a real edge, so a declared load can FAIL a rule.
5. A PASS of a rule that the stated effect of an applied door would hold is never a plain PASS.
   The frame names it in `assumed` with the door sites and each applied declaration in
   `door_reach`. The text and the page print "PASS assuming the declared reach of N doors".

**Premise of a declaration** (the claim of the contract, per site): the code that the door runs
imports only modules below `loads` through the import system as it is, changes names only of
the modules below `changes` (its own module too), and replaces no entry of `sys.modules`, no
import hook and no builtin.

**Why it is sound.** AD-564 shows that a PASS on the written facts is a PASS on the true facts
when each effect names all that its gap can change. Under the premise the door changes the code
(`E` and `C`) of the modules below `changes` only: the new effect names them. It adds edges of
its own module only to the modules below `loads`: the declared imports name each of them, so
`E` of the door module is the written set. No replaced entry means that an import of any module
still gives the module that it names. A binding that another module imports could run the door
there without an edge; such a declaration does not apply. A declared reach does not resolve an
unresolved import that the door gap covers (a TypeScript run-time key blocks the free standard
names), so such a declaration does not apply. Without a declaration the effect stays
`every_module`.

**Rejected.** A plain PASS with a note: a CI job reads only the word. An implicit `changes` of
the door module: a sandboxed `eval` changes nothing. A pickler or a door module: not in the list.

**Measured** (main `75129e008` with this change; one example declaration for each declarable
door, `loads: []`; rules PASS/UNKNOWN are the same before and after): pydantic 9 doors, 9 applied,
1/4; graphql 2, 1 applied, 1 refused (its gap covers 397 blocked names), 1/7; CE 7, 5 applied, 2
`unmatched` (a string `"__import__"` in a set is no door), 176/100; ee 23, 21 applied, 2
`unmatched`, 256/223. Other `every_module` gaps hold the same rules (CE 35, ee 72, pydantic 55
door-class gaps that are no declarable door: `__builtins__`, `types.FunctionType`, `import pickle`).

**Limits.** The premise is not checked. A TypeScript key stays UNKNOWN (point 3). The census
narrowings K4 (a) to (c) are not in this change.

**Tests.** `contract/src/door_reach_tests.rs`, `model/src/door_reach_tests.rs`,
`eval/src/door_reach_tests.rs` (undeclared door, applied, FAIL by a declared load, `changes`,
each defect), `survey/hazards_door.rs`, `report/src/html_blocks_tests.rs`,
`tests/test_cli_python_door_reach.py` (four plants through the release core; `python3` runs the
door of each one).
