# AD-1 Analyzer modules are flat and single-purpose

Originally, analyzer modules stayed flat and had one responsibility. The digest hashed only
top-level Python files; nested code could change behavior without changing identity. Splits needed a
responsibility seam and digest coverage, not a length target.

The later collector/Core split replaces that layout:
[AD-148](ad-148-source-facts-and-core-evaluation-have-separate-owners.md). Digest behavior is
covered by [test_analyzer.py](../../../tests/test_analyzer.py).
