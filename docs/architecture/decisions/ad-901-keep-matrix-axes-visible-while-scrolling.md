# AD-901: Keep matrix axes visible while scrolling

The 29-module Python shell did not fit in the Health check drawer at 1260 × 904 pixels.
The drawer and the matrix scrolled separately. The labels disappeared when the reader
scrolled to the cells. AD-889's module-count limit did not account for the available space.

The matrix replaces the diagram in the same scope. A switch returns to the diagram
without changing the scope or selection. The matrix uses one scroll area with fixed
row and column headers. A selected cell opens its directed relationships in the
same view. A button returns to the matrix. A single module relationship also opens
the existing fact sheet.
Module headers still open their module fact sheets. A single relationship keeps its Core status.

The matrix shows individual modules up to 60 modules. The Explorer's lower grouping
threshold does not change the matrix resolution. The existing hierarchy groups larger
levels. At most 60 groups give at most 3,600 table
positions. More groups ask the reader to open a smaller scope. Empty positions state no
exclusion. No relationship is inferred from the position.

We reject a module-count cutoff for an inline matrix: labels and viewport space vary.
We reject a second scroll area inside the drawer: it hides the axes and the fact sheet.
We reject a modal matrix: it covers the Explorer instead of replacing its diagram.
`tests/test_report_explorer_matrix.py` checks the real system report at desktop and
mobile widths, the 29-module shell, a small level, the Rust core and the return path.
