# Native Dart collector

Run `archkeel-dart-setup` once after installing ArchKeel. It prepares the pinned Analyzer dependencies. Scans never download packages or write into the scanned project.

The collector reads one protocol 2.0.0 request from stdin and writes one response to stdout. It analyzes a private snapshot copy and emits the shared SourceFacts wire format.
