# AD-698: Written Any annotations are partial signals

## Status

Accepted for the Python survey.

## Decision

The survey records an `any_annotation` signal for a written `Any` name or attribute inside a
variable, parameter or return annotation. The signal carries the annotation text, lexical owner
and source location. This is a syntactic finding: it does not assert what the name binds at runtime.

The capability is partial, not supported. An alias, quoted annotation or type comment can name
an opaque type without spelling `Any` in the parsed annotation. A rule can fail on a seen
annotation, but cannot pass from their absence. The store refuses a supported claim.

## Checks

`test_cli_python_profile_limits.py` checks written variable, parameter and nested return
annotations, an alias, a quoted annotation and a use outside annotations. The store test checks
that partial is accepted and supported is refused.
