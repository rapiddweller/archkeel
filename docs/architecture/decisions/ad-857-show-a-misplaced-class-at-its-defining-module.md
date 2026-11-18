# AD-857: Show a misplaced class at its defining module

## Context

The `symbol_placement` violation names the observed class, its defining module and its evidence.
The report read the class as an importer and the defining module as the imported module (#1812).

## Decision

1. Group placement findings by defining module and class, separate from imports.
2. Attribute the finding to the component of the defining module.
3. Show the recorded class and the cited locations in the existing finding. State when no location is recorded.

The report reads the frame of the snapshot. It does not read source files.
The existing limits on findings and displayed locations apply. This adds no inventory to the page.
An unsupported placement rule supplies no class finding. A pair gap does not identify a class or method.

## Verification

`a_misplaced_class_belongs_to_its_defining_module_and_cites_only_its_evidence`
checks the Explorer owner, the finding block and the missing location.
