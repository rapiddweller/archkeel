# AD-13 Mermaid diagrams are checked before GitHub renders them

Check every Mermaid fence locally with the repository parser and in CI with the pinned official
renderer. Local syntax checks are fast; renderer acceptance catches grammar and rendering
differences the parser cannot prove.

Proof: [test_mermaid.py](../../../tests/test_mermaid.py).
