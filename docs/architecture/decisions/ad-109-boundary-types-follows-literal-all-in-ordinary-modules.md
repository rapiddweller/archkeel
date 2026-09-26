# AD-109 `boundary_types` follows literal exports from ordinary modules

`boundary_types` may follow an imported facade entry from an ordinary module when one unchanged
literal `__all__` exports it, the import binding is unique, and its terminal definition has one
unambiguous module binding. The rule checks that definition's signature and reports the declared
facade as the subject. An exported import with incomplete proof contributes UNKNOWN, even when
another local function in the same module is decidable.

Every alias hop and endpoint needs proof. Candidate paths stay internal and never populate
proven IR origins, chains or facade types. A missing, ambiguous, or unproven public alias route
records `boundary_type_route` UNKNOWN, not invented parameter positions. The analyzer does not
scan an external endpoint to settle it. A constant or class is a known non-function endpoint only
while its module binding is stable. Conditional bindings, deletion, assignment expressions,
wildcard imports and explicit global rebinding cannot establish that proof. Ordinary local names do not change a
module binding. This is static binding evidence, not a proof of arbitrary runtime mutation.

A signature type is public when its owner declares its definition or a proven facade export of
that exact definition. A renamed export counts; another component's export does not make the
owner's private type public. Without a proven public route, a matching uncertain route stays UNKNOWN.
An unrelated uncertain route does not suppress a known private-type violation. Declared fields are
still checked through the same type evaluator; a public export is not an exemption for broad fields.

Reason: package `__init__.py` is not the only place a component can declare a public facade.
Rejected: treating every ordinary import as a re-export, which would guess intent and can choose
the wrong origin after rebinding. A missing or ambiguous proof remains UNKNOWN; this does not
resolve dynamic exports, local/conditional `__all__`, or arbitrary module attributes.

Check: `tests/test_boundary_types_non_init_facades.py`,
`tests/test_boundary_types_reexport_proofs.py`, `tests/test_boundary_types_chain_proof.py`,
`tests/test_boundary_types_facades.py`, `tests/test_boundary_type_finding_ids.py`, and the
ordinary-facade variants in `fixtures/demo_catalog_types.py`.
