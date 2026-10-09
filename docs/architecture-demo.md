# Architecture demos

Create a report with several deliberate violations:

```sh
make demo-architecture VARIANT=tour OUTPUT=build/demo.json
```

Use a new output path. The command validates, then writes report JSON and HTML.
Its exit is the higher validation/report exit; read the report's verdict separately.

For Python, Dart and TypeScript UML examples:

```sh
make demo-uml OUTPUT=build/uml-demo
```

Dart has independent Target PASS, signature/member and dependency FAIL, and partial-resolution
UNKNOWN cases. TypeScript includes PASS, FAIL and UNKNOWN UML cases; unsupported or ambiguous
source facts stay UNKNOWN.

Flutter adds a nested shop journey with source-only signature, enum-member, dependency, dynamic,
and unsupported-declaration cases. The base keeps external framework and inferred-type facts
UNKNOWN rather than treating them as resolved relationships.

Python adds the complete pinned FastAPI RealWorld app (72 Python modules) with architecture,
deep field-signature, and login-call variants. Its source coverage is complete; external UML
facts remain UNKNOWN.

Nest/Mikro adds the pinned RealWorld application with 41 prepared build inputs and source-only
dependency, `ArticleService.findFeed` signature, and `UserService.create` constructor variants.
Computed ORM imports, module/export aliases, framework decorators/DI, partial member and
parameter-property inventory, and `EntityManager` type/value identity ambiguity remain UNKNOWN.

| Variant | Expected evidence |
|---|---|
| `flutter-shop` | Local comparison passes; unresolved source facts keep UML UNKNOWN. |
| `flutter-signature-fail` | `OrderLine.lineTotalCents` signature FAIL. |
| `flutter-missing-member-fail` | `OrderStatus.completed` existence FAIL. |
| `flutter-forbidden-dependency-fail` | `complete_requires` FAIL for presentation → data. |
| `flutter-dynamic-unknown` | Dynamic `watchAll` call remains UNKNOWN. |
| `flutter-unsupported-declaration` | Extension yields a coverage gap and UNKNOWN observation. |
| `python-realworld-forbidden-edge` | Route imports SQL directly; rule FAIL. |
| `python-realworld-signature-fail` | `Article.tags` changes to `List[int]`; UML FAIL. |
| `python-realworld-dynamic-unknown` | `getattr` login call; UNKNOWN. |
| `nest-realworld-forbidden-edge` | Shared validation imports `Article`; `REQUIRES-COMPLETE` FAIL. |
| `nest-realworld-signature-fail` | `ArticleService.findFeed` return type changes; UML FAIL. |
| `nest-realworld-dynamic-unknown` | Type assertion makes the `User` creates relation UNKNOWN. |

The [catalog](../fixtures/architecture_demo.py) owns all variants, overlays and expected
outcomes. Check-protocol and test-only variants cannot replay as reports.
[Tests](../tests/test_architecture_demo.py) verify the catalog; the guide omits its full inventory.

Regenerate this page: `uv run --locked python -m fixtures.architecture_demo --markdown`.
