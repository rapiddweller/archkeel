# AD-29 A function that does nothing is a claim, not a stub

`placeholder_body` treats `pass`, `...` and lone `raise NotImplementedError` as
one forbidden construct; records retain the spelling. A placeholder leaves callers
built against an unimplemented promise.

Exempt `@abstractmethod`, `@overload` and methods of classes with bases, where an
interface or deliberate empty override can be legitimate. The shared emptiness
predicate lives in `source.py`, already imported by both collectors. This avoids
duplication and peer imports ([AD-25](ad-25-peers-are-isolated-by-one-rule-not-by-nn1-prohibitions.md)).
Check: the self-rule passes its two empty `Protocol` methods; bare `pass` fails.
