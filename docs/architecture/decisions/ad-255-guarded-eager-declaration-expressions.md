# AD-255 Guarded eager declaration expressions

The Python guarded-effect source walk checks expressions evaluated while a
nested declaration is created: function defaults and decorators, and class
decorators and bases. It does not evaluate postponed annotations. Deferred
function bodies remain outside the enclosing guard path.

Class bodies are visited for eager effects, but their calls currently lack a
source-replayable enclosing-function path receipt. Such a finding remains
UNKNOWN until the collector can preserve that provenance; it must not become a
proven PASS or a definite violation based only on a relabeled source scope.
