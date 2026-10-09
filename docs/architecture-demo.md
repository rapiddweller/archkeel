# Architecture demos

## Full-project journeys

The [published gallery](https://rapiddweller.github.io/archkeel/demos/) groups each pinned
application with its baseline and three source-only variants. Observation, coverage, declared
rules and UML comparison are shown separately.

- **Compass booking** — [flutter/samples@5541c59ab8e9d7e74c1a35ef22bd43a487fc596c](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c), 111 Dart files, 89 libraries, 22 parts. Authentication through search, results, activities and booking, backed by repositories and local/remote services. Target: Feature ownership, nested booking components, and closed class/member APIs. Evidence limit: Thirty typed source-resolution gaps leave coverage incomplete; they are not confirmed syntax errors.
- **Python RealWorld** — [nsidnev/fastapi-realworld-example-app@029eb7781c60d5f563ee8990a0cbfb79b244538c](https://github.com/nsidnev/fastapi-realworld-example-app/tree/029eb7781c60d5f563ee8990a0cbfb79b244538c), 72 Python modules from the complete selected application. Authentication, users, profiles, articles, comments, favorites and feeds through routes, asyncpg SQL repositories and persistence. Target: Five responsibility areas with closed principal class and method scopes. Evidence limit: All files have AST coverage; 34 class inventories and 13 inheritance relationships remain UNKNOWN.
- **Nest RealWorld** — [mikro-orm/nestjs-realworld-example-app@a6818d84b6a019cf2df4ef391dc87cea7d02c6a9](https://github.com/mikro-orm/nestjs-realworld-example-app/tree/a6818d84b6a019cf2df4ef391dc87cea7d02c6a9), 41 prepared TypeScript build inputs, including two README-prescribed config copies. Account/authentication, article and comment publishing, profile/follow, tags, composition and persistence. Target: Seven root responsibilities, nested feature components, and 266 Target entities with closed principal member scopes. Evidence limit: A computed dynamic import leaves source coverage incomplete; a known complete-requires FAIL remains visible in its forbidden-edge variant.

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
