// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A planted fault for the test of the extraction invariant (`imports.rs`, `check_extracted`).
//! `tests/test_collector_native_unextracted.py` sets `ARCHKEEL_PLANT_SKIP` to `<file>:<index>`
//! and the extraction skips that reference, as a bug in it would. The release binary has no such
//! hook: it exists only with the test feature `dump`.

/// Whether the extraction must skip the reference with this index in this file.
#[cfg(feature = "dump")]
pub fn skip(rel: &str, index: usize) -> bool {
    std::env::var("ARCHKEEL_PLANT_SKIP").is_ok_and(|planted| planted == format!("{rel}:{index}"))
}

/// The release binary skips nothing.
#[cfg(not(feature = "dump"))]
pub fn skip(_rel: &str, _index: usize) -> bool {
    false
}

/// Whether the scan must lose the nodes of this list (`import`, `export`, `dynamic`, `require`),
/// as a bug in `scan.rs` would. The invariant counts the nodes with a query apart from the scan,
/// so it must see the loss.
#[cfg(feature = "dump")]
pub fn lose(list: &str) -> bool {
    std::env::var("ARCHKEEL_PLANT_SCAN").is_ok_and(|planted| planted == list)
}

/// The release binary loses nothing.
#[cfg(not(feature = "dump"))]
pub fn lose(_list: &str) -> bool {
    false
}
