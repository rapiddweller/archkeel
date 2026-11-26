// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnmutsig`: it holds only the other signature.

pub fn run() {
    let plain: Box<dyn Fn(i64)> = Box::new(|_| {});
    drop(plain);
}
