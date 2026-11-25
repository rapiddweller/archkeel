// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The control `unbound`: it holds a `Box<dyn Any>` of another type, so `dyn Any` is in its reach.

pub fn run() {
    let value: Box<dyn std::any::Any> = Box::new(crate::unbound_c::Z);
    drop(value);
}
