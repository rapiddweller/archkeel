# AD-168 Global API intent keeps its declaration evidence

Retain global `public_api` selectors with declaration IDs and provenance
in Target. Core authenticates them against held declarations; canonical and independent
producers agree. Older graphs without this field remain readable.

Source-derived types cannot enter this intent. Selectors define neither classes,
signatures nor language visibility, and add no existence rule. Missing provenance
is invalid. Global API declarations remain unsupported inside nested contracts;
they cannot silently become component API intent.

[API Target proof](../../../tests/test_target_graph.py).
