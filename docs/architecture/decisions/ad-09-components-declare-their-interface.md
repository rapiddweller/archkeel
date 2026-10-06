# AD-9 Components declare their interface

Components declare their public modules or symbols. Cross-component imports must use that boundary,
including re-exports. Module entries expose non-underscore names or literal `__all__`; symbol
entries expose one name. Underscore names never qualify. `TYPE_CHECKING` imports count unless
explicitly excluded.

External consumers have a separate promise:
[AD-66](ad-66-declarationspublicapi-names-a-consumer-outside-the-package.md). Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
