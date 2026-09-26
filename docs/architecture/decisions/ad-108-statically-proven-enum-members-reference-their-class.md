# AD-108: Statically proven enum members reference their class

`Enum.MEMBER` counts as a reference to `Enum` only when static analysis resolves
the class and confirms `MEMBER` in its recorded literal members. This covers
field annotations, defaults and constructor arguments without executing code or
exempting every enum. Other evidence, including an explicit import, keeps its
existing meaning.

Reason: the dotted resolver names `Enum.MEMBER`, which is not a symbol; the claim
therefore missed real enum-class uses. Rejected: exempt every enum, which would
hide genuinely unused classes. Limit: enum-member evidence is considered only
for one direct module-level class or import binding with no competing binder
anywhere in that module. A binder in an unrelated scope can therefore suppress
otherwise valid evidence; type-parameter declarations conservatively suppress it
for the whole module too. These bounds avoid guessing Python lexical scope
without building a second resolver. Exact class/member resolution is still
required, and no code is executed.

Check: `tests/test_references.py` covers annotations, defaults, constructor
arguments, unused enums, unknown members, and competing parameter, class,
assignment, lambda, comprehension, exception and match binders.
