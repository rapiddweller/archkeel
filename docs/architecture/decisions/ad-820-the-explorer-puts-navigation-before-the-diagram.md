# AD-820 The Explorer puts navigation before the diagram

Status. Accepted. Issues #1770, #1771, #1772, and #1773.

The controls above and to the left of the diagram come before it in the document.
The tab order follows that placement without custom tab indices. The system-level
switch counts parts. Inside a part, the switch counts components.

A double-click, Enter, or Open on a box fits the whole level it opens.
This uses the same fit as Fit overview. A link to a level still starts at the
readable zoom floor. The whole diagram can be too small to read at first. The
user can zoom in.

The Details button keeps its name. It uses its existing expanded state to report
whether it controls an open fact sheet.

A custom tab order duplicates the order of the controls. A readable minimum when
opening a box can hide its relationships. A name that includes the state repeats
information that the button already exposes.

The browser tests in `tests/test_report_explorer_state.py` and
`tests/test_report_explorer_layout.py` check the control order, the labels, the
Details state, and the bounds of the diagram after a double-click.
