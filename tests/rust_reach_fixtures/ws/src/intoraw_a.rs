// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `intoraw`: a dependency drops the value of a raw pointer.

pub fn run() {
    regdep::drop_raw(crate::intoraw_c::leak());
}
