// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Erases a value to `dyn Any`: the coercion is here, and no body of `fx` shows it.

pub fn erase_any<T: std::any::Any>(value: T) -> Box<dyn std::any::Any> {
    Box::new(value)
}
