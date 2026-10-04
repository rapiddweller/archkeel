# Shared architecture renderer

The first stage shared SVG cards and routing. AD-179 replaces its remaining
parallel inputs with one `ArchitectureReport` and one scene projector.

Current implementation and open work: [shared UML model](2026-10-03-shared-uml-model.md).
The renderer owns layout and interaction. Core owns evidence and verdicts.
