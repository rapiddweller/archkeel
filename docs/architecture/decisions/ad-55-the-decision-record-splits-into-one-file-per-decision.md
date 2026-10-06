# AD-55 The decision record splits into one file per decision, indexed in document order

Keep one Markdown file per decision, stable IDs and filenames, and one canonical archive index. The
architecture page links that index and retains contract provenance and graph markers. Separate
records make changes reviewable without renumbering history or maintaining competing inventories.

Index/file parity is checked by
[test_repository_hygiene.py](../../../tests/test_repository_hygiene.py).
