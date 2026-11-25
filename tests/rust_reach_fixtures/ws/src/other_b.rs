// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the control `other`: the type implements a trait that `other_a` never holds.

use crate::api;

pub struct X;

pub trait Other {
    fn run(&self);
}

impl Other for X {
    fn run(&self) {
        api::hit(16);
    }
}
