# AD-51 A result carries its violations grouped by rule and by crossed component pair

Derive violation counts once by rule and ordered component pair. Use explicit source/target modules;
sorted subjects cannot prove direction. Include the breakdown on report and validation results,
including rejected runs.

Constructs, cycles and unowned crossings may lack a pair, so pair counts need not sum to the total.
Proof: [test_decisions.py](../../../tests/test_decisions.py).
