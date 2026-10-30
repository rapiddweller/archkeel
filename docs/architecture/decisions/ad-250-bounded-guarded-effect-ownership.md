# AD-250 Bounded guarded effect ownership

Evaluate selected effects against a declared Boolean parameter or member using typed source paths. The first slice covers truth and negation, `if`/`else`, conditional expressions, and paths dominated by `return` or `raise`. Core consumes admitted evidence and never reparses or executes project source.

One unique private, undecorated helper may be followed when its actual arguments bind to the observed signature. Substitution is call-site specific, so opposite paths retain separate outcomes. Canonical call identity names the effect; helper spelling and import text do not.

The limit is deliberate. Reassignment, named expressions, short-circuit Boolean operators, loops, exception/finally control flow, reflection, ambiguous declarations, helper chains and recursion cannot certify a path. They remain UNKNOWN, while any independently proven forbidden effect remains FAIL. This is not general control-flow analysis or cryptographic quality certification.

A class body and a definition header (default value, annotation, decorator, class base and class keyword) run when their statement runs, so a call there makes a member guard UNKNOWN, and a store of the guard name in a class body makes any guard UNKNOWN, even when that store is class-local. A class statement also runs hooks after its body (`__init_subclass__`, a metaclass, `__set_name__`), so a class with a base, a keyword or a non-literal field makes a member guard UNKNOWN. A class body that declares the guard name `global` or `nonlocal`, or binds it anywhere, gives no branch value.

The source facts, Core substitution and replay receipts are checked by `tests/test_guard_paths.py`, `tests/test_guarded_effect_source.py`, `tests/test_guarded_effect_evaluation.py`, and the guarded-effect codec and saved-report tests.

The reader verifies each known path by replaying the same bounded grammar over the exact enclosing-function excerpt, anchored to the call and guard source locations. A call after an `if`/`else` may carry both continuing path values; indentation alone cannot establish branch polarity. Context over the bounded evidence limit makes only that guard proof UNKNOWN.
