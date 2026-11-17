# AD-700 Rust module roots own their package

**Status.** Accepted. Part of #880.

**Reason.** The collector placed every crate root in the namespace above its crate. This grouped
unrelated crates into one package and made misleading package roll-up cycles.

**Decision.** A crate target root and a `mod.rs` file own their module package. A flat module file
that declares a child module also owns its module package. A leaf file belongs to the package of
its parent module. The collector uses the same package for file, import and symbol facts. The
manifest module stays in the crate package.

**Limit.** Rust has crates and modules, not ArchKeel packages. The package is a grouping of module
files, not a Cargo package or a compiler object. The collector reports gaps for module files that
it cannot resolve.

**Tests.** `module_files_and_edges_use_the_package_of_their_rust_module` checks the file, import
and symbol facts. The same flat and folder module files compile with `rustc`.
