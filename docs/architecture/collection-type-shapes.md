# Collection and union type shapes

Core collection descent reads the carried TypeApplication and its children from TypeShapeIndex.
Python collection owns syntax parsing; Core retains the existing container-name and import-binding
policy. Missing, malformed or non-application shapes cannot authorize collection descent.
Ellipsis remains tuple arity. No Core parser or executable parser callback is introduced.

The collection helper has a required TypeShapeIndex port. Native collector/Core cases and the
actual authored Target protect that port and the conservative missing-fact behavior.

Union and combined-position ports retain TypeShape children. Proven Optional[T] syntax supplies
an explicit TypeLiteral with LiteralKind.NONE; that child needs no invented Source record or
index lookup. Literal-string children retain their original kind. Text is read only by the
existing name/policy boundaries, and absent or unsupported syntax remains undecided.
