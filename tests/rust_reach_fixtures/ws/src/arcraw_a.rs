// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `arcraw`: a dependency calls a function pointer on the erased pointer of an `Arc`.

pub fn run() {
    let (data, function) = crate::arcraw_c::parts();
    regdep::call(function, data);
}
