// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The generic guard of the case `dropgen`: its destructor runs for the type that it holds.

use crate::api::Tr;

pub struct Guard<T: Tr>(pub T);

impl<T: Tr> Drop for Guard<T> {
    fn drop(&mut self) {
        self.0.hit();
    }
}
