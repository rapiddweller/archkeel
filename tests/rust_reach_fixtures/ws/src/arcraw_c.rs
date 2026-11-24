// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `arcraw`: `Arc::into_raw`, then a cast that erases the type.

use std::sync::Arc;

fn release(data: *const ()) {
    // SAFETY: `data` comes from `Arc::into_raw` of `parts`.
    unsafe { drop(Arc::from_raw(data as *const crate::arcraw_b::X)) }
}

pub fn parts() -> (*const (), fn(*const ())) {
    (Arc::into_raw(Arc::new(crate::arcraw_b::X)) as *const (), release)
}
