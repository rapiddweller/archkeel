// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `gvec`: a generic function over a slice of `&dyn Debug`.

pub fn all<T: std::fmt::Debug>(values: &[T]) -> usize {
    values.iter().map(|v| format!("{v:?}").len()).sum()
}
