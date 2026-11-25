// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `bptr`: the pointer is a `*mut u8` and says nothing of the value.

pub struct Handle {
    data: *mut u8,
    release: fn(*mut u8),
}

fn release(data: *mut u8) {
    // SAFETY: `data` comes from `Box::into_raw` of `make`.
    unsafe { drop(Box::from_raw(data as *mut crate::bptr_b::X)) }
}

impl Handle {
    pub fn go(self) {
        (self.release)(self.data);
    }
}

pub fn make() -> Handle {
    Handle {
        data: Box::into_raw(Box::new(crate::bptr_b::X)) as *mut u8,
        release,
    }
}
