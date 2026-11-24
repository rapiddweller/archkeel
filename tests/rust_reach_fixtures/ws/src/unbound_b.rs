// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the control `unbound`: the value of this type goes only into a `Vec` that is forgotten.

pub struct X;

impl Drop for X {
    fn drop(&mut self) {
        crate::api::hit(38);
    }
}
