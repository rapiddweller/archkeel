# AD-194 Language demos retain capability gaps

Historical scope: Dart's original import-only demo was replaced by the Analyzer-backed source
demo in [AD-211](ad-211-dart-source-facts-use-the-official-analyzer.md).

Use independent UML Targets and the shared renderer for Python, Dart and TypeScript
demos. Python observes inner definitions; Dart and TypeScript currently supply
imports, so unsupported inner comparisons remain UNKNOWN.

Target stays navigable without copying declarations into As-Is. Real module
existence checks still reject wrong names; unavailable inner capability cannot
hide them. Preserve path identities and recorded coverage. `make demo-uml` uses
existing commands and fresh output paths, proving no cross-language parity.

[Demo proof](../../../tests/test_uml_demo.py).
