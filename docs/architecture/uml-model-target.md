# UML model target

> **Main.** This page describes the comparison of release 4.0.1. The Rust core on main does not
> compare the target with the source facts yet. It writes the target row as UNKNOWN with its cause
> and never as PASS or FAIL ([AD-470](decisions/ad-470-the-uml-target-is-an-unknown-row-of-the-core.md)).

Core compares independently declared Target intent with recorded source facts.
As-Is, Target and Diff share one authenticated `ArchitectureReport` and renderer.
A diagram changes no verdict.

Use `declarations.uml` in contract 2.2 to declare entities, relationships and
scope completeness. Existing component IDs own architectural parents; declarations
cannot redeclare them or assert observed evidence. Planned entities need
responsibility and provenance. See the independent example in
Target tests and the
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
static assignment sites. The IR Target includes the bounded shared source-path
grammar used to collect and replay guarded-effect paths. Classifier, attribute
and instance coverage remains partial. The Python-hosted Dart collector records
declarations, members, signatures and bounded source relationships. TypeScript
records lexical declarations and statically bound relationships. Static sites do
not prove live object identity, lifetime, runtime dispatch or composition;
unsupported and unresolved facts stay UNKNOWN.
Complete native Dart/TypeScript direct-member inventories can prove their closed
owner scopes under unrelated resolver gaps, using bound local source evidence
([AD-229](decisions/ad-229-local-member-inventory-proof.md)). Every selected input
must be read and parsed, and the owner's library and owned parts must be free of
gaps. Inherited/generated members, unresolved traits and overall observation
completion retain their existing limits.

Contract 2.1 retains its original bytes and digest; UML requires 2.2. Graph/Target
format 1.1.0 adds enum literals; 1.0.0 remains readable with its original vocabulary.
Shared dataclasses own the format.
The dataclasses, the schema generator and the demo targets are deleted with the Python engine
([AD-432](decisions/ad-432-the-rust-core-is-the-only-decision-path.md)); the committed schemas in `schema/` stay.

[Demo coverage #339](https://github.com/rapiddweller/archkeel/issues/339) and
[independent inner Targets #340](https://github.com/rapiddweller/archkeel/issues/340)
track remaining work. See [adapter ownership](language-adapter-target.md).
