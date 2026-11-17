# AD-828: The mobile Explorer reserves space for its controls

Status: accepted. Part of #880.

On a narrow screen the content choice is cut off. The perspective bar covers the fact sheet.
Opening the sheet also changes the diagram size without fitting the diagram to that size.

Below 600 CSS pixels, the Explorer puts the content choice on its own row. It reserves separate
spaces for the diagram, the scrollable fact sheet and the perspective and zoom controls.
Opening the fact sheet fits the diagram to the remaining space. The user can still zoom and pan.
The desktop layout does not change.

The embedded Explorer is taller on a narrow screen. The user scrolls the report to reach its
lower controls. An expanded Explorer keeps the size of the screen. A very short screen can still
leave little space for the diagram.

The alternative of placing the controls over the sheet was rejected: it hides facts and actions.
The browser regression in `tests/test_report_explorer_layout.py` checks the narrow layout and
the module navigation.
