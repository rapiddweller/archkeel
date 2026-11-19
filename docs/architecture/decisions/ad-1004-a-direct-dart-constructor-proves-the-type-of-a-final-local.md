# AD-1004 A direct Dart constructor proves the type of a final local

**Status.** Proposed. Extends AD-998.

**Decision.** For an untyped final local, the linked collector can prove the static type from
its initializer. The initializer must be one direct, unprefixed generative constructor call.
The constructor must resolve to one source class with no type parameters. The local must be in
the outer body of a top-level function with no type parameters. The class declaration is in
the same library or a direct import. A visible conditional import leaves the type open.

The UML comparison uses a written annotation first. If none exists, the proof can satisfy
a target that uses the inferred type spelling. Other spellings remain UNKNOWN.

**Reason.** Dart infers the type of the local from the complete constructor expression.
The source wrote no annotation. A separate fact preserves that distinction.

**Limits.** Alias, factory, generic, shadowed and ambiguous bindings give no proof.
The proof does not resolve an alternative target spelling. It exists only in the linked
collector. The published wire schema stays the same.

**Rejected.** Use the construction relationship as a static type. It records the class of
a value and does not prove the type of every binding that can hold it.

**Checks.** The Dart collector test checks the linked proof, its absence from the wire, and
the excluded constructor forms. The CLI checks a match, an open comparison and a mismatch
against a written annotation. The unchanged Flutter shop has 26 undecided UML assessments,
down from 35.
