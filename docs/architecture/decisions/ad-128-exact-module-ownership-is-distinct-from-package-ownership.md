# AD-128 Exact module ownership stays distinct from recursive packages

`components[].packages` continues to own a package and every descendant. Optional
`components[].exact_modules` owns only each listed dotted module name, and may stand alone when
nonempty. One shared ownership predicate combines both selectors; if selectors from multiple
components match an observed module, ownership is ambiguous. There is no selector precedence, and
coverage counts owning components rather than matching selectors.

The exact identity remains separate from package prefixes through observations, nested contracts,
Actual, Target and Diff. A missing exact name is missing work; a descendant does not satisfy it.
Recursive parents may contain recursive or exact child claims. Exact parents may contain only the
same exact child claim. Existing interface, dependency, type, cycle and complete-assignment checks
continue to use the same owner result.

An unqualified `allowed_dependency` or `forbidden_dependency` rule whose endpoints each name a
uniquely declared package selector decides that whole ordered component pair, including exact
members of either component. One package-endpoint rule is sufficient; no selector cross-product is
required. A submodule endpoint or `target_symbol` is partial and does not close the pair or grant a
whole Target edge. Exact-only pairs remain open under member rules unless `complete_requires`
provides the explicit closed-world policy. Archkeel does not generate automatic dependency-rule
suggestions for pairs involving exact ownership.

Absent and empty `exact_modules` normalize identically, preserving legacy canonical bytes and
digests. Explicit null, malformed or duplicate names are invalid. `packages` may be empty only
when exact names are present; the existing namespace constraint remains package-based. Exact
references participate in digest-bound widening and in proven package rename rewriting (AD-105).

Focused contract, analyzer and report tests demonstrate the behavior (#211). No new Dart analysis
claims are made. The analyzer version advances to 0.63.0 (AD-3).
