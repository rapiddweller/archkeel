# AD-59 A type crossing many component boundaries is a review claim, not a verdict

Cross-component type fan-in is a review claim, not a verdict. Report types crossing at least two
distinct pairs, counting each function once per ordered pair. Use raw annotations; missing import or
annotation signals means UNKNOWN with no candidates.

Equal annotation spellings can merge unrelated types, and unresolved re-exports can be invisible.
Shared IR types may legitimately cross many boundaries. Proof:
[test_type_fanin.py](../../../tests/test_type_fanin.py).
