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

7. **The rule, from the shapes alone.** The model reads the `public` list of each component
   (`boundary_positions.rs`), below the `source` of the rule and outside `allowed_sources` and
   `exact_sources`. A facade module covers the names of its literal `__all__` and nothing else: a
   module with no literal list is the gap `dynamic_exports`, because a decorated function has no
   record and a list built from the records could pass it by. An entry `module:name` covers that
   name. Each covered name follows its one plain import to the definition (at most eight hops). A
   position is named by the facade name (`facade_module.name`, `facade_module.Class.method`), as
   the exceptions of a contract name it, not by the module that defines it.
8. **Positions.** The parameters and the return of each function and method that a covered name
   reaches. The receiver of a method that is not static is no position; a constructor has no
   return position (the Python collector now writes the kind `constructor` for `__init__`; the UML
   model reads no modifier from it). A class is read only when each member that it binds has a
   record, an attribute declaration or a nested class (`class_members`, written by the collector),
   and no base is a class of the repository: else one gap `member_no_record` or `inherited_surface`.
9. **One verdict for each leaf.** A scalar, `None`, a plain literal and an enum are allowed. A
   mapping (`dict[...]`, `Mapping[...]`) and `object` are broad: a violation. A class of the
   repository that no component declares is a violation. A declared class that is not an enum is
   the gap `field_walk` (the reference engine walks its fields; syntax does not). `Any` is the gap
   `any_type`: release 4.0.1 passes it, and a FAIL would be a false FAIL on a clean repository. An
   alias, a user generic, a forward reference, a type outside the scan, a name with no record, a
   dotted name and a missing annotation are each a gap with a cause. The text of the gap is the
   written type, so an accepted list binds what was written.
10. **Exceptions.** An exception (`allowed_positions`) matches a position by its name and the exact
    text of its annotation. A plain one allows the one broad leaf that is the position itself.
    Release 4.0.1 needs a second exception, with `container_depth`, for a leaf inside a collection;
    the core reads each exception with a depth, a field, an alias, a key alias, a literal arm or a
    native mapping as the gap `allowance_not_read` and never as an exception. An exception that no
    position uses is the hygiene row `boundary_type_allowance_stale`, when the surface has no gap.
11. **Verdict.** FAIL: one position is a violation with no exception (a fact also in an
    incomplete scope). UNKNOWN: no violation and one gap. The receipt of the rule holds the PASS
    back, and each gap is one hygiene row `boundary_type_position` with the subject
    `<facade name>:<position>` and the reason `<cause>: <written type>`. PASS: the scope proof of
    the model holds (every file parsed, no pair gap) and the surface has no gap. A reply of a
    profile that writes no shape is a limit of the run for each such rule.

**Soundness.** Each PASS position has a written shape whose leaves are all a scalar, `None`, a
plain literal, an enum or a collection of those. A name reaches an enum only through the binding
that the collector proved, never through its spelling: a builtin that no statement of the module
binds, one plain `def`, `class` or import that no other statement of the module binds (AD-504). A
decorated function, a class with a base outside the builtins, a name under a condition, a star
import and a module with a hazard have no record, and an absent record is a gap. The plants of
`tests/boundary_types_plants.py` run release 4.0.1 and the core on the same 55 trees: the core
never gives PASS where the release gives FAIL or UNKNOWN, never PASS where the truth is not PASS and
never FAIL where the truth is not FAIL. 37 rows are equal; 10 are a PASS of the release that the
core reads as UNKNOWN (an alias, a type outside the scan, a decorated function, a facade with no
literal `__all__`, `Any` and the like: the release passes them without proof); 8 are a FAIL of the
release that the core reads as UNKNOWN (a DTO field walk, an inherited member, a callable type).

**Rejected.**
- **Text only, parsed in the model.** The model would name a language.
- **`ast.unparse` in the collector.** The writer is a test and dump tool; the forms of an
  annotation are few, so `shape_text.rs` writes them and nothing else.
- **Allowing a type outside the scan.** Release 4.0.1 passes it. The core names the gap: the
  accepted list of the baseline then binds the written type.

**Not decided here.** `@dataclass` as a class kind (C1b), the field walk of a declared class, the
alias follow and the exceptions with a depth: the type-facts layer of 5.1.
