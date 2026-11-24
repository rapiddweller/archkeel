// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `fhold`.

pub struct X;

impl regdep::Super for X {
    fn hit(&self) {
        crate::api::hit(58);
    }
}

impl regdep::Sub for X {}
