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

/// Whether the scan must lose this thing (`reference`, `call` or `method`).
pub(crate) fn lose(kind: &str) -> bool {
    static LOST: AtomicBool = AtomicBool::new(false);
    planted("ARCHKEEL_PLANT_SCAN").is_some_and(|value| value == kind)
        && !LOST.swap(true, Ordering::Relaxed)
}
