# AD-28 An undeclared external dependency is a hole, not a detail

`complete_external_scope` requires imports outside scanned modules and the interpreter standard
library to have declared external scope. Undeclared imports produce violations naming the importer.
Resolve the standard library from the interpreter, so reproducibility and comparability include that
runtime input.

Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
