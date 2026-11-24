// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `hand`: the pointer and the function hide the type; the handle runs them.

pub struct Handle {
    data: *mut (),
    release: fn(*mut ()),
}

fn release(data: *mut ()) {
    // SAFETY: `data` comes from `Box::into_raw` of `make`.
    unsafe { drop(Box::from_raw(data as *mut crate::hand_b::X)) }
}

impl Handle {
    pub fn go(self) {
        (self.release)(self.data);
    }
}

pub fn make() -> Handle {
    Handle {
        data: Box::into_raw(Box::new(crate::hand_b::X)) as *mut (),
        release,
    }
}
