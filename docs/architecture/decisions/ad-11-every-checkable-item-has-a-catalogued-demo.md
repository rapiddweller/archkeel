# AD-11 Every checkable item has a catalogued demo

Keep demonstrable rule kinds, diagnostic codes and protocol outcomes in one typed replay catalog
with expected results. Dedicated tests cover cases that cannot be meaningfully demonstrated. Replay
logic reads that catalog; the generated guide links to it instead of repeating outcomes.

Permission declarations need no invented failure demo. Proof:
[test_architecture_demo.py](../../../tests/test_architecture_demo.py).
