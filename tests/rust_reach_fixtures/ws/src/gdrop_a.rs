// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `gdrop`: a generic guard calls a method of its field when it drops.

use crate::api::Tr;

pub struct Guard<T: Tr>(pub T);

impl<T: Tr> Drop for Guard<T> {
    fn drop(&mut self) {
        self.0.hit();
    }
}
