# AD-100 An unresolved-call change names its call sites

Explain unresolved-call changes with rows derived from existing evidence. Match identities by file,
caller and expression, excluding lines; retain occurrence counts and candidate locations. Identical
occurrences remain indistinguishable.

Scan reference code only for failing moved call budgets. Exclude added sites outside Git's
tracked/unignored scan listing or omitted by reference export rules. Unusable revisions or
inconsistent totals leave rows null. Explanations never alter verdicts. Dart has no call
measurement. Proof: [test_unresolved_call_sites.py](../../../tests/test_unresolved_call_sites.py).
