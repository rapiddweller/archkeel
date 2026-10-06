# AD-62 An annotated variable's owner is the scope it is written in, not its bare name

Typing-signal owners include the enclosing module, class and function chain. A variable annotation
belongs to its write scope, including literal attribute/subscript text; do not infer receiver
ownership from that text.

Bare variable names missed scoped rules and nested methods. Shared scope traversal fixes ownership
without a second index. Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
