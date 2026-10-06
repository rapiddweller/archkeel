# AD-22 The analyzer is a process port with a language profile

Use a versioned stdin/stdout process port for collectors. Collectors return facts; Core validates
capabilities, coverage and provenance, then evaluates policy into canonical IR. Keep diagnostics off
the fact channel.

Language support must state what it cannot observe; import facts alone prove neither API usage nor
runtime interaction. Proof: [test_collection_process.py](../../../tests/test_collection_process.py)
and [test_collection_conformance.py](../../../tests/test_collection_conformance.py).
