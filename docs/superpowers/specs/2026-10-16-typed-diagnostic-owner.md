# Typed diagnostic owner design

Expanded #542 requires parser/protocol control to use shared nominal types. The approved bounded increment extracts only diagnostic values and invariants from ir.model into ir.diagnostics. Result, comparison, amendment and command control are separate increments.

The new owner contains DiagnosticKind (the existing11 wire values), DiagnosticCode (the existing32 wire values), immutable Diagnostic and ReportLocation values, and DiagnosticError. model keeps explicit identically named reexports of exactly those same classes. Existing valid constructor strings normalize once to owned enum members; actual production producers and decisions consume enum members. Invalid kind/code messages, contract_invalid/code consistency, nonempty prose, single-line remedy and JSON Pointer checks retain their behavior. Real strings remain data.

No command schema, wire version, arbitrary record vocabulary or status domain is added. Historical diagnostic/result schemas and valid output bytes remain unchanged. There is no generic converter and no new component hierarchy. ir.diagnostics belongs to the existing governance responsibility. Its whole module is guarded; model and unrelated consumers are not certified as wholly migrated.

The independent Target specifies the new owner, two enum identities, frozen values and their field/constructor annotations. Source widening and raw dispatch mutations run with unchanged authored intent. Real self-observation compares exact before/after position identities, nested diagnostic progress and call sites; no new debt, cap or allowance is accepted. Parent integrates separate Version/RuleGrammar deltas and obtains independent Astra review.
