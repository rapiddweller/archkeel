// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `blanket`: a generic function calls a method of the associated type of a blanket impl.

use crate::api::Tr;

pub trait Tag {}

pub trait Make {
    type Item: Tr;
    fn make() -> Self::Item;
}

pub fn run<T: Make>() {
    T::make().hit();
}
