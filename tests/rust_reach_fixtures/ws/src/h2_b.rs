// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `h2`.

use crate::api;

pub struct X;

impl regdep::Plugin for X {
    fn hit(&self) {
        api::hit(2);
    }
}
