# AD-108: Statically proven enum members reference their class

Count `Enum.MEMBER` as a class reference only when static analysis proves
the class binding and recorded literal member. Exempting enums would hide unused classes.

Use and definition need unique direct module bindings. Competing binders and
overlapping writes/deletes invalidate evidence; the conservative module check may
reject unrelated scoped binders. Alias copying and dynamic mutation remain unproved.
Explicit imports retain their meaning.

[Reference proof](../../../tests/test_references.py).
