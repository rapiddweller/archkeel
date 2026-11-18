# AD-884 Dart test exclusion is an explicit source scope

**Decision.** A Dart scan with `exclude_test_sources = true` excludes selected `.dart` files
inside `test` or `tests` directories, and files ending in `_test.dart`. The rule starts at the
selected root, not at its parent project directories. A selected root named `test` or `tests`
is a test directory unless it is a Dart package directory. A nested directory with a
`pubspec.yaml` is not a test directory only because its name is `test`. The default remains false,
as AD-313 requires.

The collector names every excluded file in the live result. The core carries those names into
JSON, text and HTML, and combines the names from each system part. An import or part directive
that reaches an excluded source stays a `DartTargetNotSelected` gap. A scope that contains only
excluded files stays UNKNOWN.
After package discovery, the exclusion runs before module naming and collision checks. An
excluded path need not be a valid module name. A collision among selected files stays UNKNOWN.
The shell still recognizes the `scan` refusal of an older collector.

**Reason.** A production view must not treat test dependencies as production dependencies.
The user must see the exact sources that the scan leaves out.

**Alternatives.** A default exclusion changes existing governance scopes and is rejected.
A match on `test` anywhere in a path can exclude a production project named `test`.
Silently dropping imports into excluded code can give a false PASS.

**Limit.** The naming rule is a convention, not proof that a file is a test. Other test names
remain selected. This change does not add Dart support to Explore or Studio and does not close
issue #874.

**Check.** Dart collector plants cover the opt-in, production names, project folders and an empty
production scope. CLI plants cover the default, both verdicts, named exclusions and a production
import into an excluded source. The system test keeps exclusions from both parts.
The collision and invalid-path plants check both the default and opt-in scopes.
