// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnsig`: it holds only the other signature.

pub fn run() {
    let plain: Box<dyn Fn(i16)> = Box::new(|_| {});
    drop(plain);
}
