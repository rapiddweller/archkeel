// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `upcast`.

use crate::api::{self, Sub, Tr};

pub struct X;

pub static X_VALUE: X = X;

impl Tr for X {
    fn hit(&self) {
        api::hit(6);
    }
}

impl Sub for X {}
