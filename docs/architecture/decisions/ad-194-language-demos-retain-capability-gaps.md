# AD-194 Language demos retain capability gaps

Python, Dart and TypeScript demos use ordinary validate/report commands, independent
Contract 2.2 Targets and the shared graph renderer. Each Target names source files,
classifiers, members, operations, visibility, static bindings, aliases and constants.
Relations distinguish imports, calls, references, inheritance, realization and creation.

Python currently observes these inner examples. Dart and TypeScript collectors publish
imports, not inner definitions or calls. Their Target diagrams remain navigable; Core
records unsupported inner comparisons as UNKNOWN. As-Is shows actual modules/imports
and recorded unavailable coverage in Details. No declarations are copied into As-Is.

make demo-uml orchestrates the existing adapter and demo targets. It uses fresh output
paths. Browser acceptance checks each language, all three views and supported drill-downs.
The complete own-repository Target and cross-language collector parity remain open.

TypeScript module identities retain the collector's path codec. Module card labels
use recorded/declared filenames; complete identities remain in Details. Native tests
require module existence matches, so an unsupported inner profile cannot hide a wrong
Target module name behind UNKNOWN.
