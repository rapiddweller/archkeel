# AD-889: Keep large module matrices readable

The Health check matrix reduced large cells to 2.4 pixels and hid module labels.
Expanded mode also hid the Health check because the same content had moved into a drawer.

Draw the module matrix in the Health check for at most 60 modules. At 12 pixels per cell,
60 modules need 720 pixels per axis before labels. For larger levels, open a separate
matrix that groups modules by the existing component and directory hierarchy.
Only observed module relationships create filled cells. A cell opens its directed list
of module relationships. An empty position does not prove that an import is excluded.
The separate matrix works without the Fullscreen API and returns to the Health check.
If a level has more than 60 groups, the matrix asks for a smaller Explorer scope.
Hide the original map-column content in expanded mode, not the drawer content.

We reject shrinking the grid to fit: it removes the labels and makes cells hard to select.
The matrix uses the current level's existing groups. It does not add a new hierarchy.
The matrix axes scroll with the grid. A focused or selected cell shows both full names.
Long axis labels are shortened to limit the space above and beside the grid.

`tests/test_report_explorer_matrix.py` checks a real system report at desktop and mobile
widths, grouped relationships, the small matrix and the expanded fallback.
