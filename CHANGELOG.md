# Changelog

## Unreleased

- Remove the Python TypeScript analyzer, its parser dependency and its standard-library assets.
  TypeScript now requires the verified native collector. There is no Python fallback.
- Publish native wheels at the next owner-started release for Linux glibc x86_64/aarch64,
  Linux musl x86_64, macOS x86_64/arm64 and Windows x86_64.
  A pure wheel, sdist or editable install has no native binary.
  TypeScript scans on these installs stop with `typescript_collector_missing_binary` and exit code 2.
  Use a supported native wheel or run `make typescript-collector` from a source checkout.
- Bind native dependency-scope receipts to this run's verified bundled executable digest.
  Configured or unverified native collectors cannot certify these partial scopes.
