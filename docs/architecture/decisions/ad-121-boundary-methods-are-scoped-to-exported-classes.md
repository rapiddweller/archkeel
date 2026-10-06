# AD-121 `boundary_types` checks methods of exported classes

Check public methods, constructors and special methods only for classes proven
through the declared facade. Receiver positions follow resolved method kind;
variadics never become receivers. Overloads and framework exemptions require stable,
unshadowed bindings.

[AD-145](ad-145-local-inherited-methods-use-the-existing-base-proof.md) adds proven
local inheritance chains. Unproved MROs, mutations and decorators remain UNKNOWN;
inherited fields supply candidate usage only. Public return exposure counts as
interface use; private methods and unpublished classes do not.

[Publication proof](../../../tests/test_class_method_publication.py) and
[inheritance proof](../../../tests/test_local_inherited_methods.py).
