# AD-46 `validate --write-graph` regenerates the marked component graph after a contract edit

`validate --write-graph` replaces only one eligible marked Mermaid body with deterministic observed
edges. Preserve text outside the block. Missing, duplicate or unsupported markers fail visibly
rather than guessing a rewrite target.

Graph writing records observation and may occur despite unrelated validation diagnostics; it does
not approve policy. Proof: [test_validation.py](../../../tests/test_validation.py).
