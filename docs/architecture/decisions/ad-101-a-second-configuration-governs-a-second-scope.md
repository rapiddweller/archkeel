# AD-101 A second configuration governs a second scope at the same root

`report` and `validate --config` select one root-relative scan configuration per run. Separate
product and test scopes need separate files and outputs; results name scan roots. A green scan
proves nothing about a neighboring scope.

Product imports are external to a test scan; product-module rule targets cannot cross its namespace.
Multi-scope `check` is not added. Proof: [test_config.py](../../../tests/test_config.py).
