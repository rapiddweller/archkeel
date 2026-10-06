# AD-65 A type a declared facade signature exposes is a used public entry

A public type is used when a cross-component import or declared facade signature exposes it.
Consumers can pass values without importing their type names; treating those declarations as unused
contradicts boundary policy.

Record resolved exposure once and reuse it. Exposure proves a promise, not an observed consumer.
Planned entries do not count. [AD-69](ad-69-one-annotation-is-read-once-for-both-readers.md) unifies
annotation readers. Proof: [test_validation.py](../../../tests/test_validation.py).
