// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The control `generic`: generic code that is instantiated only with the other type.

use crate::api::Tr;

pub fn call_hit<T: Tr + Default>() {
    T::default().hit();
}

pub fn run() {
    call_hit::<crate::generic_c::Y>();
}
