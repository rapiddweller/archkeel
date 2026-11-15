# AD-542 Dart isolate and package keys need evidence

**Status.** Proposed. Part of #880. Amends AD-454 and AD-500.

**Amended by AD-562.** Selected loader and mirror identifiers give gaps without a direct SDK edge.

**Decision.** The Dart survey reads the identifiers of every selected source. A `dart:isolate`
edge gives `DartIsolate` when any selected source has an identifier `spawnUri`, or a directive
names `dart:mirrors`. A parse or budget failure keeps the gap. Otherwise the edge stays without
the gap. A string or comment is not an identifier. A dynamic call and a tear-off still name the
member. `noSuchMethod` cannot invoke a static member by a string. `Function.apply` needs a
function value; without mirrors its acquisition names the member. `Isolate.spawn` takes an
entry function, not a URI. Deferred imports retain their normal import edges.

**Premise.** Code outside the scan roots does not load or run scanned code from a name passed as
data. An external function can otherwise call `Isolate.spawnUri` on a URI from the scanned code.
The report must state this premise. The stated-premise mechanism is a separate change; merge
this decision after it lands and wire this premise into the scope text.

The package survey uses `saphyr` to parse one bounded YAML document. Only that survey may use
the parser. A key `path` gives a gap; a word in a value
does not. Invalid, complex, escaped or over-budget YAML keeps a gap. A root workspace is complete
only for simple, unique members outside every scan root. Each member manifest is an input. An
import of a member, a path mapping, an override, a link, a lock file, a package configuration or
a missing member keeps a gap. A package with `resolution: workspace` keeps a gap. Other workspace
and path forms remain UNKNOWN. An imported member stays UNKNOWN because a link below its `lib/`
can point back into a scan root. A configured external package can use such a link as well. The
survey does not read external source trees.

**Reason.** Importing an SDK library does not itself load a script. A metadata value is not a
dependency key. A disjoint unused workspace member is external to the selected source roots.

**Rejected.** Drop the isolate gap on every import: a URI loader can hide a forbidden edge.
Treat every workspace as complete: a member or override can map into the selected sources.

**Source.** Dart SDK 3.12.2 `dart:isolate` lists `spawnUri` as the script-URI loader; `spawn`
and `run` take functions. See https://github.com/dart-lang/sdk/blob/3.12.2/sdk/lib/isolate/isolate.dart.

**Tests.** `import_survey/review_tests.rs`, `survey_tests.rs` and `package.rs` plant the loader,
ports, parts, exports, mirrors, the premise, package keys, workspaces and refused forms.
