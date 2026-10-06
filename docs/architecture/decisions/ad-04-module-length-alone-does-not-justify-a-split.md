# AD-4 Module length alone does not justify a split

Split modules only at a responsibility seam. Length alone does not justify moving code or adding
interfaces. The model and codec own the analyzer/IR contract; changing that contract requires a
deliberate decision, while reorganizing unrelated helpers does not.

Proof: [test_self.py](../../../tests/test_self.py).
