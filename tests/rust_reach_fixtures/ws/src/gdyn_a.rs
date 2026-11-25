// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `gdyn`: a generic function that an instance with `Box<dyn Debug>` runs.

pub fn show<T: std::fmt::Debug>(value: T) -> usize {
    format!("{value:?}").len()
}
