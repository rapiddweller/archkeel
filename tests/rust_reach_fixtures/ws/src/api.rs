// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The traits that the cases share, and the counter that proves a dispatch.

use std::sync::atomic::{AtomicUsize, Ordering};

pub trait Tr: Send {
    fn hit(&self);
}

pub trait Sub: Tr {}

pub static HITS: [AtomicUsize; 80] = [const { AtomicUsize::new(0) }; 80];

pub fn hit(index: usize) {
    HITS[index].fetch_add(1, Ordering::SeqCst);
}

pub fn hits(index: usize) -> usize {
    HITS[index].load(Ordering::SeqCst)
}
