// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Dart grammar of the native Dart collector (AD-342).
//!
//! The C parser is vendored from the sdist of tree-sitter-dart 0.1.0 (MIT), the grammar that the
//! Python collector loads. This crate only gives the language. It does not parse and it does not
//! collect facts: a collector crate does that with `tree-sitter`.

#![deny(unreachable_pub)]

use tree_sitter_language::LanguageFn;

extern "C" {
    fn tree_sitter_dart() -> *const ();
}

/// The Dart language. Give it to `tree_sitter::Parser::set_language` with `.into()`.
// SAFETY: `tree_sitter_dart` is the generated C function of the vendored parser. It takes no
// argument and returns a pointer to a static `TSLanguage`, as `LanguageFn` requires.
#[allow(unsafe_code, reason = "AD-342: the one link to the vendored C parser")]
pub const LANGUAGE: LanguageFn = unsafe { LanguageFn::from_raw(tree_sitter_dart) };

#[cfg(test)]
mod tests;
