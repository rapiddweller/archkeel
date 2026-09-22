# AD-87: Compatibility shims are declared, logic-free and time-bounded

Moving a module can break imports outside the repository. A top-level `declarations.compat`
entry names the old module, its target and either `permanent` or `migration` lifetime.

The old module and target must differ. The analyzer proves a declared shim from existing module
and import facts: its body contains only imports and one literal `__all__`, every exported name
resolves only to the declared target, and scanned product modules do not import it. Multiple import
paths to that same target are deterministic; a second distinct origin makes the contract invalid.
Missing or incomplete evidence fails closed. Migration shims appear in ArchitectureIR and the HTML
report as a deterministic remaining-work count and module list; permanent shims do not. Adding a
shim, changing its target, or promoting migration to permanent is a contract widening under
`--against`.

Evidence: `src/archkeel/ir/model.py`, `src/archkeel/ir/codec.py`,
`src/archkeel/check/validation.py`, `tests/test_compatibility.py`.
