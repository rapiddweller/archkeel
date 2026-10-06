# AD-73 The external surface is judged by the same walk

Judge external API signatures and annotated class fields through the shared boundary-type walk.
Resolve declaration origins too, so re-exported types match their definitions. Missing resolved
owned types produce `api_surface.missing`; unscanned library types are not undeclared package
promises.

Unresolved shapes retain the walk's UNKNOWN limits. `__init__` assignments are not annotated
class-field evidence. Proof:
[test_public_api_boundary.py](../../../tests/test_public_api_boundary.py).
