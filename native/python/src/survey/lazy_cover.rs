// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the lazy import proof of one module covers (AD-560): the leaf that `hazards.rs` reads.

use ruff_text_size::TextRange;

/// What the proof of one module covers: the ranges of the sites that are no gap and the import
/// targets of the calls.
#[derive(Default)]
pub(super) struct Lazy {
    pub exempt: Vec<TextRange>,
    pub targets: Vec<(TextRange, String)>,
}
