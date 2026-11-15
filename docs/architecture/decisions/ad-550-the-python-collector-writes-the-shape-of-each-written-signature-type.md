# AD-550 The Python collector writes the shape of each written signature type

**Status.** Proposed. Part of #880. Slice C of the CE package (L-221). It extends AD-518 and
amends the schema rule of AD-345.

**Reason.** Release 4.0.1 checks the written types of the public API of a component
(`boundary_types`). The core had no fact for it: an annotation is text, and the model does not
parse a language. The owner decided that the syntax half ships in 5.0.0 and the type-facts layer
in 5.1 (L-221). What syntax cannot decide is a named gap, never PASS.

**Decision.**
1. **One closed tree.** `archkeel-facts::type_shape::TypeShape` is the written type of one
   position. It names no language: a scalar, a type that holds anything, a collection (sequence or
   mapping family, with its arguments), a union, a literal, an annotated type, a name with its
   binding, a name applied to arguments, a forward reference, a missing annotation and an
   unreadable form. Each node holds its text in the form of `ast.unparse`, because an exact
   exception of a rule matches that text. A form with no such text is `unreadable`, never a guess.
2. **Where it is.** `Parameter.shape` for each parameter and `CallableData.returns_shape` for the
   return, written for each function and method that has a record (AD-518). The two fields are
   absent when a collector writes no shapes (`Profile::type_shapes`, true for Python only). The
   model reads absent shapes as "not written", a named gap, never as plain.
3. **Binding, not spelling.** A name carries `builtin` when it is a builtin class that no
   statement of the module binds (star imports, type parameters and the names of the class body
   count as binders), `defined` or `imported` when exactly one plain statement of the module body
   binds it (the rule of AD-504), and else `unproven` with a cause: `star_import`, `hidden`,
   `not_sole`, `unread_import`, `unbound`, `dotted`. A dotted name is proven only as one attribute
   of one plain module import. The special forms (`Optional`, `Union`, `Annotated`, `Literal`,
   `Any`) and the collections are read by the target of their binding, so `Optional = list` in
   another module is not `typing.Optional`. A string annotation is read only for `str` and
   `object` (as in 4.0.1); any other string is `forward`.
4. **An unwritable text no longer withholds the module.** AD-518 gave no record for any
   declaration of a module when one signature held a text that native does not write (`list[int]`
   is one). Almost every module of a typed project is such a module. Now the callable keeps its
   record with `signature_complete: false` and no text; the UML model reads that as "not decided"
   (`uml_details::signature`). The shapes carry what was written. No record gets a wrong text.
5. **Classes.** A class with a decorator (`@dataclass`) has no record (AD-518 rule 5). A name that
   `defined` binds to such a class has no record, and the model names the gap `unresolved_name`.
   Admitting `@dataclass` as a class kind is not part of this decision.
6. **Schema.** `archkeel-facts-9.schema.json` is regenerated. The schema is not published: no
   release ships it (4.0.1 ships `source-facts.schema.json`), and #1108 changed it in place the
   same way. Both new fields are optional, so each reply that exists stays valid.

**Rejected.**
- **Text only, parsed in the model.** The model would name a language.
- **`ast.unparse` in the collector.** The writer is a test and dump tool; the forms of an
  annotation are few, so `shape_text.rs` writes them and nothing else.

**Not decided here.** The rule itself (model and eval): see the second part of this record.
