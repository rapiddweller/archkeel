# AD-412 The native Python source facts have explicit record inputs

**Status.** Proposed. Part of #880. AD-412 is free in the open-PR file inventory.

**Reason.** The source fact modules need a compared lexical index before runtime assembly.
The measurement finds inputs that are not source helpers. Do not replace those inputs with
guessed symbol or call results.

**Measurement.** `scopes.py` reads `symtable`, binding kinds, source locations, definition ids
and control-flow contexts. `typing_signals.py` reads source annotation text and evidence;
its dynamic and boundary functions read call, import and symbol records. `state.py` reads
source paths, decorators and class ownership; its assembly reads symbol flags and node maps.
`private_attributes.py` reads source helpers and the import alias map. `type_shapes.py` reads
quoted source expressions and effective context-manager signatures from symbol records.
The PR gives the function-by-function measurement for all five files.

**Decision.**
1. Add lexical, typing-signal and state dump boundaries under the existing `dump` feature.
   Keep record inputs explicit. Do not call `resolve.py`, member convergence or `calls.py`.
2. Compare complete results with the unchanged Python functions on Python 3.11 to 3.14.
   Preserve traversal order, record identities, evidence and every field.
3. Keep production replies unchanged. The store still refuses them until #1072 closes.
4. Charge input loops against the existing bounded scan. Refuse a whole file on exhaustion.
   Keep existing text depth and serialized output limits. Keep no partial result on refusal.
5. Keep private corpus data out of files and diagnostics. Report aggregate counts only.

**Rejected.** A Python subprocess inside the native collector; guessed receiver ownership;
partial production sections; and empty call or symbol inputs presented as complete assembly.

**Not done yet.** Private-attribute and type-shape ports remain separate complete modules.
Cross-module resolution, call collection, member convergence and production assembly remain
outside this slice. The measured five-module plan can stop after three complete modules.

**Tests.** `test_collector_native_python_facts.py` compares dump results and bounds.
The final PR records exact work, generated branch probes, corpus counts and charge faults.
