# AD-131: Public API closure includes inherited fields

## Decision

`public_api` includes the public fields a declared class inherits through one
proven local base chain. Resolve each field in its defining module with the
existing annotation resolver. Unambiguous re-exports and bare class aliases retain their origin.
Verified generic parameters use the existing binding substitution machinery.
Subclass fields and class members override inherited fields.

Private fields, implementation methods and known framework bases do not enlarge
the declared type set. Pydantic payload fields follow the same walk.

## Why

Declaring `Child(Base)` previously passed while `Base.payload: Payload` exposed
an undeclared local type (#243). Direct fields already rejected that exposure.

| Declaration | `validate` result |
|---|---|
| `Child` alone | exit 2, `api_surface.missing` for `Payload` |
| `Child` and `Payload` | exit 0 |
| Unresolved or ambiguous inheritance | `api_surface_limit` UNKNOWN with source evidence |

## Rejected and limits

Do not reconstruct types in the checker or inspect implementation methods.
Sorted base records cannot prove multiple-base precedence; retain UNKNOWN.
Cycles, dynamic class bodies, unresolved inherited annotations and unsupported
generic arguments and unproven class aliases also retain UNKNOWN. Generic
substitution accepts bare named arguments; compound arguments need a separate
proof. Runtime model behavior is not evaluated.

## Verification

`tests/test_public_api_boundary.py` covers local and aliased entries and bases,
overrides, generic chains, Pydantic, direct-field controls, UNKNOWN evidence,
CLI results and canonical/HTML reports. `public-api-inherited-missing`,
`public-api-inherited-declared` and `public-api-inherited-unknown` are runnable
catalog demos.
