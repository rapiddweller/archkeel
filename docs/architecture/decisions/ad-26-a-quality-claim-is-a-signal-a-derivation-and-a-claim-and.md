# AD-26 A quality claim is a signal, a derivation and a claim, and never guesses

A quality claim needs a supported signal, a pure derivation and an explicit Class D interpretation.
Missing signals mean UNKNOWN with no candidates. Lexical unused-binding evidence is a review hint;
an empty candidate list does not prove all values are used or safe to delete.

Claims do not decide conformance. Proof: [test_bindings.py](../../../tests/test_bindings.py).
