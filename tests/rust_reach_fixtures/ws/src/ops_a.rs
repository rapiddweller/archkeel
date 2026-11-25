// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `ops`: a generic function that adds two values.

pub fn sum<T: std::ops::Add<Output = T>>(left: T, right: T) -> T {
    left + right
}
