# AD-208: Module import cells require evaluated import rules

Module import cells report local import evidence separately from component permission.

An observed import is `FAIL` when an applicable Core finding names that edge. It is `PASS` only
when every applicable import rule has a complete evaluator receipt and no local finding names the
edge. Otherwise it is `UNKNOWN`, with the undecided rule named when available.
Receipt subjects follow evaluator scope: `forbidden_dependency` covers the importer;
boundary-wide rules cover both modules. Sibling selectors use the evaluator's package scopes.

Declared `requires` relationships and `layer_order` checks describe permission. They do not prove
that observed imports were evaluated, so they cannot establish cell `PASS` on their own. Global
rule verdicts remain global: a rule may fail on one edge while a separately evaluated edge passes.

The cell permission field remains `UNKNOWN` until Core provides an authenticated per-module import
permission receipt.
