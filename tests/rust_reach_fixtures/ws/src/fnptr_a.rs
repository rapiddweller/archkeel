// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnptr`: it calls a function pointer with an erased pointer through a dependency.

pub fn run() {
    let (data, function) = crate::fnptr_c::parts();
    regdep::call(function, data);
}
