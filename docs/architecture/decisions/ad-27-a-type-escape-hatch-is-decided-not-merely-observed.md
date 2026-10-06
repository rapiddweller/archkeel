# AD-27 A type escape hatch is decided, not merely observed

Treat `Any` as a forbidden construct through the existing signal and allowance path. Legitimate
heterogeneous boundaries need a scoped reason; they do not justify an unchecked type throughout a
component. Keep this contract rule separate from aggregate typing measurements.

Proof: [test_analyzer.py](../../../tests/test_analyzer.py) and
[test_architecture_demo.py](../../../tests/test_architecture_demo.py).
