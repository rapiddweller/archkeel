# AD-830 `boundary_types` walks only complete, proven dataclass fields

**Status.** Accepted. Extends AD-782. Fixes #1780.

**Context.** A facade can return a declared dataclass. AD-782 lets the collector model its decorator and generated constructor under `standard_library_unchanged`. The model still returned `field_walk` for the whole type. The constructor facts do not cover every dataclass field form.

**Decision.**
1. Under `standard_library_unchanged`, walk a declared dataclass only when the collector provides its guarded `Wrapped::Class` form and generated constructor shapes.
2. Require every declared class attribute to appear in the generated constructor inventory. This rejects `ClassVar`, `init=False`, assigned attributes, and other incomplete inventories until the facts carry their types.
3. Apply the existing position gates to each field, including changed standard-library names. Then use the existing boundary rules. A broad field remains FAIL. An unresolved, unreadable, or missing field remains UNKNOWN. A recursive dataclass path remains UNKNOWN.
4. If repository code can write a field name, or can write through a namespace, the collector withholds the dataclass form. This check includes code outside the scan roots. It can also withhold a model for an instance store with the same field name.
5. Without the premise, keep the position UNKNOWN and name `standard_library_unchanged`. Do not infer a dataclass from a decorator spelling.

**Rejected.** Treating all declared classes as dataclasses would invent fields for ordinary classes. Treating the constructor parameters as a complete inventory would miss `init=False` and other class attributes.

**Limit.** The model does not walk dataclass inheritance, `ClassVar`, `InitVar`, custom constructors, `init=False`, or field writes. These cases stay UNKNOWN until the collector publishes complete field-shape facts and a narrower mutation proof.

**Tests.** `tests/test_cli_boundary_types.py` checks the #1780 fixture, premise visibility, nested dataclasses, a forbidden mapping field, unknown fields, unmodeled and changed decorators, field mutations, and recursion.
