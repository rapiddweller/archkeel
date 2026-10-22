# AD-40 A call whose callee the import binding proves, or whose receiver is already typed, types its result from a documented table

Resolve call results through a closed constructor/method table only when import bindings prove the
type. Follow results forward within the owning scope; later rebinding does not erase an earlier
result. Unlisted calls stop resolution.

This supplies partial static evidence, not project-wide type inference or runtime behavior. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py) and
[test_typed_python_receivers.py](../../../tests/test_typed_python_receivers.py).

The closed receiver table may include selected standard-library methods when the receiver type is
proven by its import binding; optional unions stay unresolved without narrowing evidence.
