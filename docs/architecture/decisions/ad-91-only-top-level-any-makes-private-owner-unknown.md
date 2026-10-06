# AD-91 Top-level owner resolution decides private ownership UNKNOWN

Resolve a private parameter's outer annotation at one shared boundary. Untyped, unresolved or proven
`Any` owners stay UNKNOWN. Nested `Any` does not erase a deterministic outer owner, and nested
arguments do not establish that owner.

Local/imported bindings are usable only with fail-closed shadowing checks. Proof:
[test_private_crossings.py](../../../tests/test_private_crossings.py).
