# AD-87: Compatibility shims are declared, logic-free and time-bounded

Declare compatibility shims with distinct old module and target, plus permanent or migration
lifetime. Prove an import-only body plus one literal `__all__`, exports to one target, and no
scanned product imports of the shim. Missing or incomplete evidence fails closed; two paths to one
origin are acceptable, distinct origins invalidate the contract.

Adding a shim, changing its target or making migration permanent widens. Migration remains reported
work. Proof: [test_compatibility.py](../../../tests/test_compatibility.py).
