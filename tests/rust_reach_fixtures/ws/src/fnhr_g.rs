// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnhr`: it takes the box as a `dyn Fn(&'static u8)` by subtyping, with no cast, and drops it.

pub fn take(value: Box<dyn Fn(&'static u8)>) {
    drop(value);
}
