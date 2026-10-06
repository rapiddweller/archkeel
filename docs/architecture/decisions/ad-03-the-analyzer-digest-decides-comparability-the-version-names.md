# AD-3 The analyzer digest decides comparability; the version names it

Comparable observations require equal analyzer `code_digest`. Equal version labels cannot prove
equal behavior; the version is a human label and changes when record meaning changes. Comparisons
must reject different digests rather than reinterpret old evidence.

Proof: [test_delta.py](../../../tests/test_delta.py).
