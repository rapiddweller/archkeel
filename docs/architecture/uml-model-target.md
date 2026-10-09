# UML model target

Core compares independently declared Target intent with recorded source facts.
As-Is, Target and Diff share one authenticated `ArchitectureReport` and renderer.
A diagram changes no verdict.

Use `declarations.uml` in contract 2.2 to declare entities, relationships and
scope completeness. Existing component IDs own architectural parents; declarations
cannot redeclare them or assert observed evidence. Planned entities need
responsibility and provenance. See the independent example in
[Target tests](../../tests/test_target_graph.py) and the
[generated schema](../../schema/architecture-contract.schema.json).

## Conformance

- Known kind, signature, visibility or parent conflicts FAIL.
- Missing entities or edges FAIL only with complete inventory and relevant
  resolution. Ambiguous definitions and unresolved calls cannot satisfy intent.
- Closed scopes reject known extras and require complete evidence before PASS.
  Partial children cannot certify an unmeasured parent inventory.
- Unavailable facts, unknown traits and empty Targets remain UNKNOWN.

Signatures compare recorded syntax, including ordered parameters and defaults;
they do not prove type equivalence. Python method Targets include `self`/`cls`.
Dependency permissions remain separate from mandatory UML calls. Proposals derived
from As-Is are drafts, not an independent oracle. UML changes pass through the
existing widening gate.

## Capabilities and compatibility

Python records definitions, members, signatures, explicit bases, contexts and
static assignment sites. Classifier, attribute and instance coverage remains
partial. The Python-hosted Dart collector records declarations, members, signatures
and bounded source relationships. TypeScript records lexical declarations and statically
bound relationships. Static sites do not prove live object identity, lifetime,
runtime dispatch or composition; unsupported and unresolved facts stay UNKNOWN.

Contract 2.1 retains its original bytes and digest; UML requires 2.2. Graph/Target
format 1.1.0 adds enum literals; 1.0.0 remains readable with its original vocabulary.
[Shared dataclasses](../../src/archkeel/ir/architecture_graph.py) own the format.
`make architecture-graph-schema` regenerates its schemas.

Replay native-language examples with `make demo-uml OUTPUT=<fresh-directory>`.
[Demo coverage #339](https://github.com/rapiddweller/archkeel/issues/339) and
[independent inner Targets #340](https://github.com/rapiddweller/archkeel/issues/340)
track remaining work. See [adapter ownership](language-adapter-target.md) and
[render ownership](render-target.md).
