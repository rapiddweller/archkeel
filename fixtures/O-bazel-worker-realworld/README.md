# bazel_worker architecture, checked at a pinned commit

This folder holds only ArchKeel's own files: the layering contract, the scan config and the
component graph. It holds no bazel_worker source. `SOURCE.json` names the pin (repository,
commit, licence). The gallery fetches that exact commit of dart-lang/tools when it builds and
scans the package `pkgs/bazel_worker`. The contract keeps `src/driver` and `src/worker` apart.
