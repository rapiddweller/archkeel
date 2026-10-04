# Shared UML model

Goal: As-Is, independent Target and Diff use one typed model and one renderer.
The old columnar Observation remains readable during the migration.

- [x] Define immutable graph dataclasses and generate their JSON Schema.
- [x] Validate IDs, parents, evidence and uncertain relationship endpoints.
- [x] Preserve Python parameter kinds/defaults, visibility and private annotated attributes.
- [x] Normalize existing source records, including cross-module calls and references.
- [x] Publish Python definition-site parents/callers; retain repeated declarations, direct nested functions and local classes.
- [x] Record conditional definitions, exact parents/callers and typed control-flow contexts; retain unproven bindings as candidates (AD-170).
- [ ] Complete lexical binding proof and publish explicit SourceFacts inventory capabilities.
- [x] Add independent Target entities, operations and typed relationships to contract codecs/schema.
- [x] Define open/closed Target scopes separately from observed coverage.
- [x] Authenticate UML intent and component owners in Core; reject invented or conflicting adapter declarations.
- [x] Retain component roles, ownership and public/planned API intent in the standard graph; authenticate owner metadata in Core.
- [x] Retain root Contract 2.2 module inventories and physical layout rules in the standard graph; share validation, authenticate intent in Core and show it without inventing UML.
- [x] Compile nested explicit UML into one authenticated Target; retain component parents and scoped inventories/layout in the common renderer.
- [x] Retain authenticated requires permissions in both Target producers; keep existing Core dependency rules as their only policy owner.
- [x] Authenticate legacy component and physical intent in one graph descriptor; preserve existing rules and receipts without implicit UML evaluation.
- [x] Retain authenticated global public API selectors and independent provenance in the standard graph; exclude source-derived exposed types.
- [x] Project legacy component details and permissions from the authenticated graph; retain repeated IDs, exact endpoints and evidence.
- [x] Decode authenticated Target once; retain repeated permissions and original Core findings (AD-176, AD-179).
- [x] Migrate legacy Target browser projections through the standard graph.
- [x] Project physical Target navigation from graph intent; define and check render responsibility boundaries (AD-178).
- [x] Remove the file-alias bridge and parallel overview/Diff payload readers.
- [x] Evaluate existence, signatures, visibility, typed relationships and completeness in Core; retain UNKNOWN where coverage or identity is missing.
- [x] Generate the comparison schema and retain typed assessment evidence in existing rule receipts.
- [x] Project explicit Python inheritance/realization with source sites, binding limits and classifier coverage.
- [x] Record direct call-result assignment sites and typed construction/instance candidates with source evidence (AD-171).
- [ ] Complete lexical classifier binding proof, other binding forms and instance-result resolution.
- [x] Replace lossy inner render data and remove redundant projections.
- [x] Render As-Is module entities and Contract 2.2 Target/Diff through the shared UML renderer; preserve Core assessments and unlisted definitions.
- [x] Display unlisted relationship overlays in Diff using typed Core correspondences and exact site evidence.
- [x] Open observed-only Diff interiors with source identity, scoped Core receipts and stable navigation.
- [x] Reuse Focus for direct UML neighbors in all views; retain complete evidence, counts, Core status and navigation (AD-174).
- [x] Use the UML legend to separate relationship kinds; retain full evidence, Core status and navigation without hidden hit areas (AD-175).
- [x] Filter standard UML element kinds through one scene; retain complete evidence and navigation, and retain original Core evidence (AD-177).
- [x] Migrate legacy intent and remove replaced payloads.
- [x] Share UML notation, layout, routes, focus and hit geometry across views.
- [x] Regenerate self-observation, report and screenshots for the shared report boundary.
- [ ] Integrate on current Main and audit the full goal against the integrated evidence.

Owners and invariants: [UML model target](../../architecture/uml-model-target.md).
Local checks precede CI. No commit, push, merge or publication without Alex's instruction.
