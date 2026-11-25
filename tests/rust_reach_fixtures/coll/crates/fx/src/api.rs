// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The counter that proves a dispatch.

use std::sync::atomic::{AtomicUsize, Ordering};

pub static HITS: [AtomicUsize; 8] = [const { AtomicUsize::new(0) }; 8];

pub fn hit(index: usize) {
    HITS[index].fetch_add(1, Ordering::SeqCst);
}

pub fn hits(index: usize) -> usize {
    HITS[index].load(Ordering::SeqCst)
}
