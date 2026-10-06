# AD-66 `declarations.public_api` names a consumer outside the package

`component.public` promises an interface to another component in the scan. `declarations.public_api`
promises one to external consumers. Reuse that separate declaration; unobserved outside consumers
cannot justify unused-entry findings.

Check module existence, declared names
([AD-71](ad-71-a-promised-name-is-checked-against-the-modules-own-all.md)) and exposed types
([AD-73](ad-73-the-external-surface-is-judged-by-the-same-walk.md)) with their respective evidence.
Proof: [test_validation.py](../../../tests/test_validation.py).
