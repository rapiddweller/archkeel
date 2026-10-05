# AD-188 Enum literals have their own UML kind

The shared graph distinguishes `enum_literal` from a class attribute. A literal
belongs to one enumeration and has no operation modifiers. Source projection
reuses the analyzer's existing conservative `enum_members` facts. It adds no enum
resolver or Target knowledge to the analyzer.

Physical attribute inventories retain their source IDs. Enum coverage remains
partial: literal assignments do not prove every effective enum member. `auto()`,
`_ignore_`, reassignments and other unsupported forms do not become guessed
literals. Core does not mistake their physical fields or value bindings for a
known wrong UML kind. A known operation still contradicts a required literal.

Graph and Target-definition format 1.1.0 introduce the new vocabulary. Readers
preserve 1.0.0 values; that version cannot carry enum-literal entities, scopes or
coverage. Core retains the newest declared format when combining inside targets.
Report and comparison envelopes keep their existing versions. Schemas come from
the dataclasses through `make architecture-graph-schema`.

The shared renderer uses a Literals compartment, bare literal names and distinct
literal cards. It does not underline literals as static attributes. Independent
Target intent now includes the five component responsibility roles and their
graph-format alias dependencies.

Assignment symbols retain Python naming visibility through the same producer as
class and operation facts. A public type alias is a naming convention, not an
enforced access boundary.

Proof: `test_enum_graph.py`, `test_uml_rendering.py`, `test_target_graph.py` and
`test_own_uml_target.py`.
