// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A place in a source file: the evidence that a fact cites.

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Site {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub excerpt: String,
}
