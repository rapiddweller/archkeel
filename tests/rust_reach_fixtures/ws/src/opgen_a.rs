// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `opgen`: a generic function calls a method of its argument.

use crate::api::Tr;

pub fn go<T: Tr>(value: T) {
    value.hit();
}
