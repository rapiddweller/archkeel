# AD-108: Statically proven enum members reference their class

`Enum.MEMBER` counts as a reference to `Enum` only when static analysis resolves
the class and confirms `MEMBER` in its recorded literal members. This covers
field annotations and defaults without executing code or exempting every enum;
unknown, dynamic, and missing members do not suppress an unreferenced-symbol
candidate.
