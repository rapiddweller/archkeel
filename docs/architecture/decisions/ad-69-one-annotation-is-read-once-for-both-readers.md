# AD-69 One annotation is read once, for both readers

Read each annotation once for both boundary judgment and facade exposure. A type judged inside a
collection must also count as exposed; separate walks had drifted and produced contradictory
unused-entry findings.

Both readers share supported shapes and UNKNOWN limits. Adding exposure resolution ahead of rule
resolution would recreate the mismatch. Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
