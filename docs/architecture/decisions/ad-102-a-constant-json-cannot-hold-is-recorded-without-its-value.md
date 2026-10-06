# AD-102: A constant JSON cannot hold is recorded without its value

Keep static constant symbols even when JSON/UTF-8 cannot encode their value. Include `constant` only
when the actual encoder accepts it. `repr` would invent a string value; dropping the symbol would
lose binding evidence.

Absent values cannot prove Literal members and remain UNKNOWN. Distinguish an absent key from the
legitimate `None` literal. Proof:
[test_boundary_type_literals_aliases.py](../../../tests/test_boundary_type_literals_aliases.py).
