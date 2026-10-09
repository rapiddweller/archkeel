# AD-214 Dart collection runs without an SDK

The user requires one Python installation for all three language collectors.
Replace AD-211's official Analyzer process with a Python-hosted Tree-sitter parser
and bounded source resolver. Keep the shared process protocol, evidence validation
and UNKNOWN semantics. Do not ship a second backend or keep native setup commands.

[Target and acceptance](../dart-python-target.md) precede implementation.
The tradeoff is ownership of bounded source resolution; this is not compiler parity.

The Python self-scan now includes the collector previously written in Dart. The
verified source digest `75b3e102a236cacbb07498f19e42af18dd708f6bbbcece7c8c8e831b62ea8399`
has 213 unresolved calls inside the new Dart collector and 702 elsewhere: 915 total,
versus the former 704 budget. These are bounded Python receiver/expression inference
limits, including standard-library and Tree-sitter calls. Record the expanded scope
with a 915-call ratchet; retain every other budget (52 typing, 53 UNKNOWN, zero
violations, cycles and private crossings). Do not add observer exceptions.
The review-candidate cap becomes 11 after deleting two unused resolver methods;
three called methods remain candidates because Python only partially resolves the
injected receiver. This is a review claim, not a verdict or dead-code proof.

[Bound amendment](ad-214-dart-python-collector-amendment.json).
