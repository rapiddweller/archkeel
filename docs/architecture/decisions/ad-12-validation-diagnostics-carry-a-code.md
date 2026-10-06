# AD-12 Validation diagnostics carry a code

Contract-invalid findings carry a stable `DiagnosticCode` and JSON pointer at construction. Codes
identify failures across renderers and replay tests; presentation text is not their identity.
Pre-validation analyzer failures remain separately identified.

Delete a code when its failure is unreachable rather than retaining dead catalog entries. Proof:
[test_architecture_demo.py](../../../tests/test_architecture_demo.py).
