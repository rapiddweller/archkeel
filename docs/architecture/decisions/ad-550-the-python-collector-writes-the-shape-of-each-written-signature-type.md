# AD-550 The Python collector writes the shape of each written signature type

**Status.** Proposed. Part of #880. Slice C of the CE package (L-221). It extends AD-518 and
amends the schema rule of AD-345.

**Reason.** Release 4.0.1 checks the written types of the public API of a component
(`boundary_types`). An annotation is text, and the model does not parse a language. The syntax
half ships in 5.0.0, the type-facts layer in 5.1 (L-221). What syntax cannot decide is a named
gap, never PASS.

**Decision.**
1. **One closed tree.** `archkeel-facts::type_shape::TypeShape` is the written type of one
   position and names no language: a scalar, a type that holds anything, a collection, a union, a
   literal, an annotated type, a name with its binding, a name with arguments, a forward
   reference, a missing annotation, an unreadable form. Each node holds its text as `ast.unparse`
   writes it, because an exact exception matches that text.
2. **Where.** `Parameter.shape` and `CallableData.returns_shape`, for each function and method
   with a record (AD-518). A collector that writes none (`Profile::type_shapes` is true for Python
   only) gives a named gap, never a plain type. `class_members` lists each name of a class body.
3. **Binding, not spelling.** A name is `builtin` when no statement of the module binds it,
   `defined` or `imported` when exactly one plain statement binds it (AD-504), else `unproven` with
   a cause. The special forms and collections are read by the target of their binding. A string
   annotation is read only for `str` and `object`; any other is `forward`.
4. **An unwritable text no longer withholds the module.** The callable keeps its record with
   `signature_complete: false`; the UML model reads that as "not decided".
5. **Classes.** A decorated class (`@dataclass`) has no record: a name bound to it is a gap.
6. **Schema.** `archkeel-facts-9.schema.json` is regenerated: no release ships it, and #1108
   changed it in place. Both fields are optional.
7. **Surface.** The model reads the `public` lists below the `source` of the rule. A facade
   module covers its literal `__all__` only (else the gap `dynamic_exports`); `module:name` covers
   that name. Each name follows its one plain import to the definition. A position carries the
   facade name, as the exceptions of a contract do.
8. **Positions.** The parameters and return of each reached function and method. No receiver, no
   return for a constructor (kind `constructor` for `__init__`). A class needs a record for each
   member and no base of the repository: else the gap `member_no_record` or `inherited_surface`.
9. **Leaves.** Scalar, `None`, plain literal, enum: allowed. Mapping, `object`: violation. A class
   that no component declares: violation. A declared non-enum class: gap `field_walk`. `Any`: gap
   `any_type` (4.0.1 passes it). Alias, user generic, forward reference, type outside the scan,
   name with no record, dotted name, missing annotation: a gap with its cause and written text.
10. **Exceptions.** An exception matches a position by name and exact text. A plain one allows the
    one broad leaf that is the position. One with a depth, field, alias or mapping is the gap
    `allowance_not_read`. An unused exception is the hygiene row `boundary_type_allowance_stale`
    when the surface has no gap.
11. **Verdict.** FAIL: a violation with no exception. UNKNOWN: no violation and one gap; each gap
    is one hygiene row `boundary_type_position` (`<facade name>:<position>`, `<cause>: <text>`).
    PASS: the scope proof holds, the surface has no gap and at least one position was read.

**Soundness.** A PASS position has a shape whose leaves are scalars, `None`, plain literals,
enums or collections of those, reached only by a binding that the collector proved. A decorated
function, a class with a base of the repository, a conditional name, a star import and a module
with a hazard have no record, and an absent record is a gap. 55 plants
(`tests/boundary_types_plants.py`) run 4.0.1 and the core: the core never gives PASS where the
release gives FAIL or UNKNOWN, and never PASS or FAIL against the truth. 37 rows are equal, 10 are
a release PASS read as UNKNOWN, 8 a release FAIL read as UNKNOWN.

**Rejected.** Text parsed in the model (it would name a language). `ast.unparse` in the collector
(`shape_text.rs` writes the few forms). Allowing a type outside the scan (4.0.1 does; the core
names the gap, so an accepted list binds the written type).

**Not decided here.** `@dataclass` as a class kind, the field walk, the alias follow and the
exceptions with a depth: the type-facts layer of 5.1.
