# Typed structure measurement levels

Issue #542 includes parser and report protocol controls.

The existing ir.structure owner defines the two report measurement levels: component and
package. They differ from rule CycleLevel (component/module) and topology (module/package).
StructureLevel becomes a nominal StrEnum in that same owner. StructureMetric and the public
scope_metrics port retain their existing shapes; supported legacy string inputs normalize
at those existing boundaries. Internal callers and both display decisions use the shared
members. Unknown levels are rejected rather than silently rendered as another scope.

Module names, package names and JSON keys remain string data. No new DTO, physical module,
record schema closure, IO, budget increase or duplicated level inventory is introduced.

Independent Target intent protects the actual metric field and scope_metrics level
parameter. Exact function guards protect oversized_insides and the renderer's structure
overview. Tests mutate consumed source while keeping authored intent fixed, retain numeric
results and JSON rendering, and exercise existing onboarding/report consumers.

Execution: real RED on the existing Literal/unnormalized field; minimal owner and consumers;
native Target and guard mutation GREEN; affected structure/onboarding/report checks; normal
integrated validation and independent final Astra before the final #542 merge.
