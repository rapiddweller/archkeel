# AD-245: A contained `requires` entry narrows

`validate --against` compares `requires` entries as a set (#634). A new entry is a widening
unless every import it permits was already permitted to the same target by an entry with
the same author (`decided_by`). Containment uses the import semantics of `requires_covers`
(AD-42): a module selector covers its submodules and their ports, a port covers only
itself, and an entry without `through` covers the whole public surface. An entry without
`through` is contained only by another entry without `through`.

Before, any `through` change was a widening, so tightening `orders.storage` to
`orders.storage:save` required an amendment. Now it narrows. A different target, a
different author, a sibling prefix (`orders.storagex`), or a selector outside the old set
still widens.

Out of scope: `exact_modules` and `packages` changes stay fail-closed widenings, including a
module that moves to another owner.

[Containment controls](../../../tests/test_widening.py)
