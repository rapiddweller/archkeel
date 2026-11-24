// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `vtreg`.

pub struct B;

impl vdep::Plugin for B {
    fn go(&self) {
        crate::api::hit(66);
    }
}
