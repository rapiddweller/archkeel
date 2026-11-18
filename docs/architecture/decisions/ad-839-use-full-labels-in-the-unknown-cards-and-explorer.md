# AD-839: Use full labels in the Unknown cards and Explorer

Status: accepted. Part of #1769.

## Context
The Unknown cards showed opaque rule IDs. Explorer cards abbreviated inventory counts and
mixed a layer description with the responsibilities of its members.

## Decision
Show each available rule kind beside its ID. Use whole words for inventory counts. Show only
the group summary on a layer card and keep the member responsibilities in Details.
Link run gaps with no component to the Unknown section.

Use only the metadata in the report frame. It gives each rule kind but carries no general
rule rationale. A rationale from another rule or from a dependency would mislead.

The report tests check the grouped reasons, rule kinds, and run-gap link. The Explorer browser
test checks the visible counts and layer summary.
