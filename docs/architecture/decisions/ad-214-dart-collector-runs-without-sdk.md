# AD-214 Dart collection runs without an SDK

The user requires one Python installation for all three language collectors.
Replace AD-211's official Analyzer process with a Python-hosted Tree-sitter parser
and bounded source resolver. Keep the shared process protocol, evidence validation
and UNKNOWN semantics. Do not ship a second backend or keep native setup commands.

[Target and acceptance](../dart-python-target.md) precede implementation.
The tradeoff is ownership of bounded source resolution; this is not compiler parity.
