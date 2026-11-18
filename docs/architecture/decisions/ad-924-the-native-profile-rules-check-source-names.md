# AD-924: The native Profile rules check source names

**Reason.** The five `NATIVE-NEUTRAL-*-NO-PROFILE` rules forbid naming `Profile`.
Running a trait implementation for that type does not, by itself, name it.
The compiler pilot found positive edges but did not prove absence for any pair.

**Decision.** Contract 3.19.0 adds `source_symbol_only` to a `target_symbol` rule.
Only the five native rules opt in. Their rationales state the predicate in the
report. A direct name, a bound alias or re-export, a glob route, a type argument,
or a pattern can name the symbol. An independently defined type alias names the
target where it is defined, not at each use of the alias (AD-668).

The Rust worker carries a private marker when a dot call records an inferred
receiver type. The source-name rule does not use that marker as a source
reference. Other rules still read the edge and its receiver. The public facts
schema does not change. A saved reply has no private receiver evidence.

Only the source-name scope sets aside gaps marked as execution alone by the
live collector, with both ends observed and owned. An open or mixed name route
still holds the rule, even when another site proves a dependency for that pair.
The coverage inventory, the cycle rules, and the interface reading do not
change. Omission of the option preserves the existing symbol rule behavior.

**Model design candidate.** `model/src/observed.rs` calls capability methods
through `facts.profile`. The field and method names do not name `Profile`, so
this is not a violation. The methods can still return different answers by
language. Give the model the typed capability values instead, if a separate
change confirms their producer and validation boundary. Do not count this
rule as a proof that the model makes no language-dependent decisions.

**Rejected.** Match the five rule IDs in code. Do not interpret gap message
text as proof. Do not use an inferred receiver or a selected impl as though
the caller wrote the type. Do not remove execution gaps from the graph.

**Check.** The Rust controls check two equal call texts with different receivers
in both orders, an alias, a glob, a type argument, a pattern, and `!=` through
the default `PartialEq::ne` body. They keep mixed and unresolved name routes open.

**Result.** On base `347f43fe1`, the reported blocking pairs went from 199 to
41 for Store, 2,723 to 439 for Model, 1,100 to 102 for Eval, 1,188 to 126 for
Report, and 6,734 to 247 for Core. All five rules remain UNKNOWN. The native
report still has 82 PASS, 0 FAIL, 10 UNKNOWN, and the same 23,015 coverage gaps.
