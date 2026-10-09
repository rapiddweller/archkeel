# Full-project architecture demos

The user rejected small examples as representative demos. Deliver three connected, real application source snapshots and independently authored Targets. Repair and merge the failing pipeline first. Then implement with Luna agents, Superpowers and Ponytail; commit, push and merge only after clean final-head CI. No legacy compatibility is required.

## Projects

| Project | Immutable revision | Complete analysis scope |
|---|---|---|
| Flutter Compass, `flutter/samples` | `5541c59ab8e9d7e74c1a35ef22bd43a487fc596c` | All 111 Dart files in `compass_app/app/lib`, including 22 generated parts; 89 logical libraries. Pubspec is configuration, not a module. |
| Python RealWorld, `nsidnev/fastapi-realworld-example-app` | `029eb7781c60d5f563ee8990a0cbfb79b244538c` | All 72 Python files under `app`, including package initializers and migrations. Preserve accompanying SQL, stub and template files. |
| TypeScript RealWorld, `mikro-orm/nestjs-realworld-example-app` | `a6818d84b6a019cf2df4ef391dc87cea7d02c6a9` | Preserve all 45 original `src` files (42 TypeScript files, two configuration templates and one migration snapshot). Upstream build config selects 39 TypeScript sources and excludes three specs. Copy the two templates exactly as prescribed by upstream setup, recording them as derived configuration inputs; analyze all 41 prepared build inputs. |

These are full application source scopes, not claims to analyze platform projects, assets, external servers, tests outside the selected runtime scope or runtime framework behavior. Python upstream is archived; it illustrates architecture, not current dependency or security recommendations.

## Required behavior

- Each base report covers the entire selected source scope and has a non-null computed comparison.
- Full selected-input coverage is distinct from complete semantic evidence. A fully inventoried source scope can retain a coverage FAIL and exit code 2 for bounded source gaps while still producing the same Core UML comparison receipt from authenticated, validated partial observations. Such a comparison must keep absent/unknown evidence UNKNOWN, permit FAIL only for observed contradictions, and never report aggregate PASS when its comparison inputs are incomplete. Invalid contracts, malformed protocols, and untrusted facts remain blocked; do not weaken `complete_requires` or claim Core coverage PASS.
- Compass includes authentication/session, routing, search/results/activities/booking, models, use cases, repositories, local/remote services, generated serialization and environment composition.
- Both RealWorld apps include users/authentication, profiles/following, articles/feed/favorites, comments/tags and persistence. Preserve their actual structure; do not insert artificial layers.
- Each Target defines high-level responsibilities, allowed dependencies, meaningful nested components, module ownership and principal class/member/relationship contracts. At least one real feature has a navigable component/subcomponent/module/class/member path.
- Targets are authored from intended responsibilities, upstream design documentation and explicit source inspection. They must not be generated from ArchKeel's observed graph. Record Target hashes before acceptance collection. All source-only variants retain those Target bytes.
- Each project demonstrates an architecture violation, a deep UML mismatch and an unresolved relationship using source-only changes with precise evidence. Baseline UNKNOWNs and intentional baseline deviations remain visible; a green whole-project badge is not required.
- Missing evidence stays UNKNOWN. Missing selected inputs or unsupported source syntax remain coverage failures; legal declarations must not be excluded merely to obtain a comparison. A non-null partial UML comparison does not convert coverage FAIL into completeness or a passing aggregate verdict.
- Fix evidenced structural collector defects at their shared source. Dart mixin declarations and `with` composition need faithful shared vocabulary; do not relabel them as inheritance. Keep external parameter types and callback/dynamic execution unproven when evidence is absent.
- Preserve original upstream bytes, licenses, immutable source URLs and hashes. Retain all generated sources. Analysis must not fetch, install dependencies or execute application code. Any dependency resolver inputs are explicit, pinned snapshot inputs.
- The public gallery leads with three named projects and explains scope, responsibilities, Target depth and limits. Group regression variants with their project. Existing small examples remain labeled rule fixtures; their count is not a project count.
- Verify meaningful As-Is, Target and Diff navigation through nested components and UML, including source evidence, on desktop and mobile. Generated overview/detail links must work.

## Acceptance evidence

Record per project: input and logical-module counts, ownership coverage, source and Target hashes, comparison availability, assessment counts, representative PASS/FAIL/UNKNOWN evidence, browser navigation results and remaining limitations. Distinguish local checks, exact-head PR CI, Main CI, publication and application runtime execution. Do not claim mobile device execution or deployed backend correctness from structural analysis.

Use existing Make, collector, evaluator, report and gallery paths. Run affected focused regressions, relevant language gates, full `make check`, architecture checks, report browser/pages checks and final independent review before publication. Measure additional CI cost and change limits only when evidence supports it.
