# AD-108: Statically proven enum members reference their class

`Enum.MEMBER` counts as a reference to `Enum` only when static analysis resolves
the class and confirms `MEMBER` in its recorded literal members. This covers
field annotations, defaults and constructor arguments without executing code or
exempting every enum. Other evidence, including an explicit import, keeps its
existing meaning.

The dotted resolver names `Enum.MEMBER`, which is not a symbol, and missed real
enum-class uses. Exempting every enum would hide unused classes. Evidence applies only
for one direct module-level class or import binding with no competing binder
anywhere in that module. A binder in an unrelated scope can therefore suppress
otherwise valid evidence; type-parameter declarations conservatively suppress it
for the whole module too. These bounds avoid guessing Python lexical scope
without building a second resolver. Exact class/member resolution is still
required. The enum's defining binding must meet the same bound. Scanned attribute
writes/deletes invalidate overlapping qualified targets; an ambiguous imported
writer suppresses the augmentation. External writes leave unrelated enums alone.
This is syntactic evidence, not proof of runtime immutability: assignments that
copy an alias and dynamic mutation are not followed.

Analyzer version 0.53.0 names the changed evidence (AD-3); package release versions
and the contract schema are separate and unchanged here.

Check: `tests/test_references.py` covers annotations, defaults, constructor
arguments, unused enums, unknown members, and competing parameter, class,
assignment, lambda, comprehension, exception and match binders independently,
plus defining-module rebindings and cross-module attribute writes/deletes.
