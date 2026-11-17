# AD-796 The Dart collector resolves names and states symbols

**Status.** Proposed. Part of #880 and #1533. It amends AD-400 (the resolver stays in Python) and
AD-468 (the survey states no symbol). Slices S2 and S3 amend this record.

**Reason.** Every Dart UML target was UNKNOWN: "the dart collector states no symbol facts, the dart
collector states no symbol sites". H-uml-dart was PASS in 4.0.1. The Rust `collection` of AD-400
already builds the 4.0.1 symbol and site records, but it reads typed answers of a resolver that
the release build did not have (`resolve.py`, 2018 lines).

**Design.** `native/dart/src/resolve.rs` is the resolver. It reads only facts that the survey
proved: a module is a library of the survey or the owner of a part. It answers the keys of the
collection (directives, names, sites, constructions) and the formals of each constructor.
`symbol_survey.rs` runs the full parse, the resolver and the collection, and the reply takes the
symbol records. The import records stay the records of the survey (AD-749).

**Basis.** The resolver reads programs that `dart analyze` accepts. The other collectors use the
same basis (AD-608). It uses that basis in two places only:
1. A declaration of the library hides an imported name of the same name.
2. A name that a project library exports through an unprefixed import is the binding, even with an
   unread import of another package. Two non-platform libraries that export one used name are a
   compile error, and a `dart:` library loses to a project library.

A name of a library outside the snapshot has no binding, so it stays unresolved and never becomes
a project declaration.

**Not ported from 4.0.1.** In `resolve.py`, an unqualified name inside a class looks up the library
before the members. Dart does the reverse, and an unknown superclass can declare any member. S2
gives such a name a gap.

**S1 (this change).**
- Namespace and constructor formals are ported: field formals, super formals and redirecting
  factories (`resolve/params.rs`). Bases and type aliases bind through `show`, `hide`, prefixes
  and `export`. Each site and each construction is `unknown`, and the reply writes no call or
  reference section. `Profile::symbol_facts` is true for Dart, and `symbol_sites` stays false.
- A class inventory is complete only when no form outside the body can add a member. A mixin
  application (`with`), a part of the library, or a project extension on the class makes it
  partial, and the reason names the form. An augmentation is a syntax gap, so its file gives no
  symbol.
- The parser reads a prefixed type (`m.Base`), which 4.0.1 read as `m`, and the `on` type of an
  extension.
- The store checks that a symbol name is the last segment of its qualified name. A named
  constructor is named `named`, not `Class.named`, and an accessor keeps its `::getter` or
  `::setter`. The qualified names stay those of 4.0.1, which the UML targets use.
- The facts gain the symbol kind and category `attribute` (a top-level variable that is not
  constant), the class kind `mixin` and the base kind `mixes_in`.

**Measure.** UML assessments undecided before and after S1: H-uml-dart 89 -> 23, I-flutter-shop
289 -> 107, J-compass 421 -> 74. Rule counts and G-dart (9/0/1) do not change. No assessment is
FAIL.

**Kept gaps (S1).** Every relationship stays UNKNOWN until S3 states sites. A local binding has
no record until S3. A collection that stops on its work limit gives no symbol, so each symbol
stays UNKNOWN.

**Undo.** Make `Profile::symbol_facts` false for Dart and drop the `symbols` section in
`import_survey/reply.rs`.
