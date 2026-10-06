# AD-29 A function that does nothing is a claim, not a stub

Detect placeholder bodies through one shared syntactic predicate. `pass`, ellipsis and lone `raise
NotImplementedError` indicate unfinished work. Exempt abstract methods, overloads and methods on
classes with bases, where an empty override may be intentional. Collector peers reuse the foundation
predicate rather than import each other.

This is static evidence, not proof of useful runtime behavior. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
