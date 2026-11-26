# AD-1135 A Rust directory below the walk depth is a named gap

**Status.** Accepted. Issue #1002 (one probe for each limit).

**Reason.** The Rust file walk (`native/rust/src/source.rs`) stops at 128 directory levels. It returned no file and no gap. The survey of the core allows 256 levels, so a repository with a directory between 129 and 256 levels reached the limit without a word. A `#[path]` attribute can load a file in such a directory. The module tree read the file, but the walk had not listed it. The reply then claimed more read files than selected files, and the store refused the whole reply with "impossible collection coverage counts". The user saw UNKNOWN for the whole contract and no cause.

**Decision.**
1. `walk` returns the files and the directories that it did not enter. The collector names one coverage gap for each such directory: "Directory is deeper than the walk reads, so its files are not scanned: <dir>".
2. A `.rs` file that the module tree claims is part of the selection, also when the walk did not list it.
3. The limit stays 128. A deeper tree is rare, and the gap tells the user to move the code.

**Rejected.**
- Raise the limit to 256. A limit still exists, and a depth between the two would be silent again.
- Refuse the scan. A gap keeps every rule that the directory cannot change.

**Limit.**
- A rule that the directory can change stays UNKNOWN. This change cannot enable a PASS.

**Tests.**
- `source::tests::a_directory_below_the_depth_limit_is_listed_as_not_entered`
- `collect::tests::a_module_file_below_the_walk_depth_is_a_named_gap_and_stays_selected`
