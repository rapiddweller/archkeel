// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `assoc`: a generic function calls a method of an associated type.

use crate::api::Tr;

pub trait Make {
    type Item: Tr + ?Sized;
    fn make() -> Box<Self::Item>;
}

pub fn run<T: Make>() {
    T::make().hit();
}
