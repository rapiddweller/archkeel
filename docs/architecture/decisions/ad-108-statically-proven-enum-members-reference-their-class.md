# AD-108: Statically proven enum members reference their class

`Enum.MEMBER` counts as a reference to `Enum` only when static analysis resolves
the class and confirms `MEMBER` in its recorded literal members. This covers
field annotations and defaults without executing code or exempting every enum;
the enum-member evidence does not resolve unknown, dynamic, non-enum, missing or
shadowed members. Other evidence, including an explicit import, keeps its existing
meaning.

Reason: the dotted resolver names `Enum.MEMBER`, which is not a symbol; the claim
therefore missed real enum-class uses. Rejected: exempt every enum, which would
hide genuinely unused classes. Limit: only an exact statically resolved class
and its recorded literal member count; no code is executed.

Check: `tests/test_references.py` covers annotations, defaults, constructor
arguments, unused enums, unknown members and parameter shadowing.
