# AD-107 A module's file is its evidence, even when the file is empty

A module's file is evidence even when empty. Use line 1 with text;
otherwise exactly line 0, end line 0, column 0 and an empty excerpt.
Empty initializers can then retain valid layout and namespace traces.

Positive lines still require source text. Only file evidence writes line 0;
structural validation cannot prove the right evidence kind was selected.
Blank files remain exempt from complete assignment.

[File proof](../../../tests/test_file_evidence.py) and
[trace validation](../../../tests/test_trace.py).
