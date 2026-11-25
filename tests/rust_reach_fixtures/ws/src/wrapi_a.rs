// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `wrapi`: it drops a `Box<dyn Any>` that the impl for `Wrapper<T>` made.

pub fn run() {
    drop(crate::wrapi_c::make());
}
