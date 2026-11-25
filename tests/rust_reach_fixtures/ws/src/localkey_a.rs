// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `localkey`: it takes a value out of a thread local.

pub fn run() {
    crate::localkey_c::KEY.with(|key| drop(key.borrow_mut().take()));
}
