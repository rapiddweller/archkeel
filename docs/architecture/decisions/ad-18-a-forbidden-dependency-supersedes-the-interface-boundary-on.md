# AD-18 A forbidden dependency supersedes the interface boundary on the same import

A forbidden dependency takes precedence over an interface finding for the same import. Report the
decisive failure once, while retaining interface checks on remaining crossings. Permitting a
component pair does not permit imports outside the provider's public boundary.

Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
