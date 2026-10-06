# AD-71 A promised name is checked against the module's own `__all__`

Check promised symbol names against a module's literal `__all__`, when available. Module existence
alone cannot prove an export; symbol records omit constants and aliases. Without literal `__all__`,
retain module-only checking and leave names unchecked.

This concerns the external API declaration, not a silent change to component-public validation.
Proof: [test_validation.py](../../../tests/test_validation.py).
