# AD-184 Annotation declarations retain lexical binding

Separate annotation declaration ownership from Python header evaluation scope.
Parameters and returns belong to an operation signature, while name resolution
uses its enclosing scope. Defaults, decorators and ordinary reads retain lexical
ownership.

Record declaration scope and definition ID together; validate them against one
method/function site in the same module. UML uses that operation as source.
Legacy records keep their scope. This adds no binding inference, policy or coverage.

[Declaration proof](../../../tests/test_source_graph.py).
