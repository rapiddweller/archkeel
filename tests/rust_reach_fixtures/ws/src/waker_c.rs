// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `waker`: a `RawWaker` with an erased data pointer and a table of function pointers.

use std::task::{RawWaker, RawWakerVTable, Waker};

static TABLE: RawWakerVTable = RawWakerVTable::new(clone, wake, wake_by_ref, release);

unsafe fn clone(data: *const ()) -> RawWaker {
    RawWaker::new(data, &TABLE)
}

unsafe fn wake(data: *const ()) {
    // SAFETY: `data` comes from `Box::into_raw` of `make`.
    unsafe { release(data) }
}

unsafe fn wake_by_ref(_data: *const ()) {}

unsafe fn release(data: *const ()) {
    // SAFETY: `data` comes from `Box::into_raw` of `make`.
    unsafe { drop(Box::from_raw(data as *mut crate::waker_b::X)) }
}

pub fn make() -> Waker {
    let data = Box::into_raw(Box::new(crate::waker_b::X)) as *const ();
    // SAFETY: the table follows the contract of `RawWakerVTable`.
    unsafe { Waker::from_raw(RawWaker::new(data, &TABLE)) }
}
