// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `intoc`: `Into<String>` through `From`.

pub struct X;

impl From<X> for String {
    fn from(_: X) -> String {
        crate::api::hit(44);
        String::new()
    }
}
