# AD-109 `boundary_types` follows literal exports from ordinary modules

`boundary_types` may follow an imported facade entry from an ordinary module when one unchanged
literal `__all__` exports it, the import binding is unique, and its terminal definition has one
unambiguous module binding. The rule checks that definition's signature and reports the declared
facade as the subject. An exported import with incomplete proof contributes UNKNOWN, even when
another local function in the same module is decidable.

Every alias hop needs proof. Candidate paths stay internal and never populate proven IR origins,
chains or facade types. An unresolved public alias cycle records `boundary_type_route` UNKNOWN,
not invented parameter positions; known constants and classes remain outside function-only scope.

Reason: package `__init__.py` is not the only place a component can declare a public facade.
Rejected: treating every ordinary import as a re-export, which would guess intent and can choose
the wrong origin after rebinding. A missing or ambiguous proof remains UNKNOWN; this does not
resolve dynamic exports, local/conditional `__all__`, or arbitrary module attributes.

Check: `tests/test_boundary_types_non_init_facades.py`,
`tests/test_boundary_types_reexport_proofs.py`, `tests/test_boundary_types_chain_proof.py`,
`tests/test_boundary_type_finding_ids.py`, and
`fixtures/demo_catalog_types.py`'s `class-a-boundary-types-ordinary-reexport`.
