# AD-45 `analyzer` declares a three-part inside, the way `check` already does (AD-20)

The original analyzer contract separated orchestration, collectors and shared foundation. Collector
isolation expressed dependencies; duplicating directory groups added no useful boundary. Package
initialization was not an inner owner and could not justify widening scope.

[AD-148](ad-148-source-facts-and-core-evaluation-have-separate-owners.md) replaces that embedded
analyzer layout with separate source-fact and Core evaluation owners.
