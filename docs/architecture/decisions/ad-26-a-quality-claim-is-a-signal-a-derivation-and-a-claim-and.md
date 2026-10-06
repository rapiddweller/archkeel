# AD-26 A quality claim is a signal, a derivation and a claim, and never guesses

Each quality claim needs an analyzer signal declared as a capability, a pure `ir`
derivation, and a Class D report claim without a verdict. Without its signal, the
derivation returns `UNKNOWN` and no candidates, like unsupported measurements
([AD-5](ad-05-invariants-live-where-values-are-built.md)).

Call and import records alone had produced 41 unreferenced-symbol candidates.
After exempting dunders, `__all__` and subclass methods, all 13 remaining candidates
were wrong: value references (`_RULE_PARSERS`, `type=_sha`), properties and outside
consumers were invisible to the graph. All 8 supposedly unimported modules were
initializers, an entry point or a subprocess target. False candidates teach readers
to skip the claim.
Check: a missing signal returns `UNKNOWN`; a value-only function reference is not
a candidate.

The second claim, `unread binding`, uses `bindings`: parameters or locals no
expression in their own function reads. It is supported wherever collection ran;
the denominator is examined functions, since skipped bindings are not measured.
The collector skips underscore names, `self` and `cls`. For parameters, it also
skips methods of classes with bases, decorated functions and empty bodies.
The last three are syntactic
heuristics, not proof of overrides or structural conformance.

This lexical fact cannot prove a parameter unnecessary or safe to remove.
An empty list means none were recorded, not that every parameter is read.
Archkeel's clean run records none because `ARG` and `RUF059` reject them at lint time.
