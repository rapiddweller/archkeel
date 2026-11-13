// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A planted fault for the test of the extraction invariant (`edges_extracted.rs`).
//! `tests/test_collector_native_rust_unextracted.py` sets `ARCHKEEL_PLANT_SKIP` to `<file>:<index>`
//! so that the edges skip that reference, `ARCHKEEL_PLANT_ARM` to `<file>:<index>` so that the arm
//! of that edge ends nothing, and `ARCHKEEL_PLANT_SCAN` to `reference`, `call` or `method` so
//! that the scan loses the first one of the process, as a bug in them would. The release binary
//! has no such hook: it exists only with the test feature `dump`.

use std::sync::atomic::{AtomicBool, Ordering};

/// The value of a plant variable. The release binary has none.
#[cfg(feature = "dump")]
fn planted(name: &str) -> Option<String> {
    std::env::var(name).ok()
}

#[cfg(not(feature = "dump"))]
fn planted(_name: &str) -> Option<String> {
    None
}

/// Whether the edges must skip the reference with this index in this file.
pub(crate) fn skip(rel: &str, index: usize) -> bool {
    planted("ARCHKEEL_PLANT_SKIP").is_some_and(|value| value == format!("{rel}:{index}"))
}

/// Whether the edges must end nothing for the edge with this index in this file, as an arm that
/// forgot to write its record would.
pub(crate) fn arm(rel: &str, index: usize) -> bool {
    planted("ARCHKEEL_PLANT_ARM").is_some_and(|value| value == format!("{rel}:{index}"))
}

/// Whether the edges must skip the method call with this index in this file.
pub(crate) fn method(rel: &str, index: usize) -> bool {
    planted("ARCHKEEL_PLANT_METHOD").is_some_and(|value| value == format!("{rel}:{index}"))
}

/// Whether the scan must lose this thing (`reference`, `call` or `method`).
pub(crate) fn lose(kind: &str) -> bool {
    static LOST: AtomicBool = AtomicBool::new(false);
    planted("ARCHKEEL_PLANT_SCAN").is_some_and(|value| value == kind)
        && !LOST.swap(true, Ordering::Relaxed)
}
