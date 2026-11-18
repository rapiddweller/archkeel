# AD-889: Keep large module matrices readable

The Health check matrix reduced large cells to 2.4 pixels and hid module labels.
Expanded mode also hid the Health check because the same content had moved into a drawer.

Use cells at least 12 pixels wide and keep both module axes. Give the matrix a bounded
scroll area. Put the group legend after the matrix, so large reports reach the grid first.
Hide the original map-column content in expanded mode, not the drawer content.

We reject shrinking the grid to fit: it removes the labels and makes cells hard to select.
We do not add a hierarchical dependency matrix; issue #783 tracks that separate work.
The grid remains an SVG, so very large reports still create one element per observed cell.
The axes scroll with the grid; they do not stay fixed when a user moves away from them.

`tests/test_report_explorer_matrix.py` checks a real system report at desktop and mobile
widths, the axis labels, scrolling and the expanded fallback.
