# Shared collector bootstrap

The analyzer Process owner publishes one is_direct_entrypoint(module_name: str) -> bool
port. Its bootstrap module converts an arbitrary incoming module name once through the
owned nominal direct-start marker. An ordinary import returns false without invoking
collector code or touching standard streams.

Python, Dart and TypeScript entries retain their known main and SystemExit sites, resolver
checks and request/response handling. Sharing only the protocol decision avoids an opaque
callback and adds no name-resolution authority. CLI startup is independent.

The authored analyzer Target pins the marker kind and public bool signature. Complete
module guards protect bootstrap and all three language entries. Native source mutations
exercise raw dispatch and type weakening without changing that Target. Runtime provenance
includes the shared bootstrap source because it contributes to every collector.
