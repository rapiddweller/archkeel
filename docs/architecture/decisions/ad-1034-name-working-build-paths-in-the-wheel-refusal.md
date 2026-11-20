# AD-1034: Name working build paths in the wheel refusal

Status: accepted.

The source distribution has no Rust sources. Its wheel build cannot use
`ARCHKEEL_BUNDLE_NATIVE=1`. The refusal names a Git checkout and `make build`,
a prebuilt core on a supported host, and the supported platform wheels.

The same message is used in a checkout. This avoids a second message for a
build failure. The build still rejects a host without a supported wheel tag.
`tests/test_collector_native_wheel.py` checks the refusal and both build paths.
