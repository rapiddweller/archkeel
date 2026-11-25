// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `fnptr`: the pointer is erased with a cast.

fn release(data: *const ()) {
    // SAFETY: `data` comes from `Box::into_raw` of `parts`.
    unsafe { drop(Box::from_raw(data as *mut crate::fnptr_b::X)) }
}

pub fn parts() -> (*const (), fn(*const ())) {
    (Box::into_raw(Box::new(crate::fnptr_b::X)) as *const (), release)
}
