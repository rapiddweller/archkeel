# AD-49 An allowance may name its module exactly, so a package root is scoped on its own

Add `exact_sources` without changing `allowed_sources` prefix semantics. External scope matches the
importing module; constructs match the owning module, class or function. Record both exemption lists
so narrow root permissions remain reviewable. Old contracts retain their meaning.

Subject-presence checks remain prefix-based and can count descendants of a missing exact module.
Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
