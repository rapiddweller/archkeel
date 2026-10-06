# AD-198 Provider use survives initializer ownership

Preserve a provider's proven use through an ancestor-published re-export when
its initializer has exact ownership. Rule evaluation and lifecycle validation
share chain coverage; both ancestor publication and unique ownership remain required.

Lifecycle evidence stays in its own mount. Unproved candidates retain UNKNOWN,
never positive use. Private or unpublished routes cannot satisfy the provider API.

[Re-export lifecycle proof](../../../tests/test_nested_facade_reexport_lifecycle.py).
