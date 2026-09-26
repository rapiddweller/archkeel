# AD-26 A quality claim is a signal, a derivation and a claim, and never guesses

Every quality
claim has three parts: a signal the analyzer records and declares as a capability, a pure derivation
in `ir`, and a Class D claim the report shows without a verdict. When the signal is missing, the
derivation reports UNKNOWN and shows no candidates, the way regression measurements exist exactly
when the comparison is SUPPORTED ([AD-5](ad-05-invariants-live-where-values-are-built.md)). Reason: deriving unreferenced symbols from call and import
records alone produced 41 candidates on Archkeel itself; after exempting dunder names, `__all__`
entries and methods of subclasses, 13 remained, and every one of them was wrong, because a function
used as a value (`_RULE_PARSERS`, `type=_sha`), a property read as an attribute and a consumer
outside the scan scope are all invisible to a call graph. The same run listed 8 modules nobody
imports, and all 8 were package `__init__` files, an entry point or a subprocess target. A claim
whose candidates are wrong every time teaches readers to skip the section, which costs more than the
missing claim. Check: a derivation without its signal returns UNKNOWN, and a probe whose function is
referenced only as a value yields no candidate. The claim set grows the same way: `unread
binding` is the second claim, and its signal is the `bindings` section, which records a parameter
or local no expression in its own function reads. That question is settled inside one scope, so
the claim is supported wherever the analyzer ran; what it cannot observe is how many bindings the
collector set aside, so it reports the functions it examined as its denominator instead of
inventing that number. The collector skips leading-underscore names, `self` and `cls`, and
parameters in methods of classes with any base, decorated functions, or empty bodies. The last
three are syntactic heuristics, not proof of an override or structural conformance. The fact is
lexical: it does not decide whether an implementation parameter is required by an interface or safe
to remove. An empty candidate list means none were recorded, not that every parameter is read. On
Archkeel itself it names nothing, because `ARG` and `RUF059` reject such a binding at lint time: a
claim that stays empty on a clean repository is working, not missing.
