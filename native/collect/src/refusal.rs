// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed refusals shared by the scan composition and the collector thread (AD-420).

/// The first words of each refusal; the shell counts them.
pub(crate) const REFUSED: &str = "collect";

/// A part that the in-process path cannot run, by name.
#[derive(Debug, PartialEq, Eq)]
pub struct Refusal {
    /// The part of the input that the collector refuses.
    pub part: &'static str,
    /// Why the collector refuses it.
    pub reason: String,
    /// How the shell must treat the refusal.
    pub kind: RefusalKind,
}

/// Whether the shell can use its stage 1 path, or must stop without an artifact.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RefusalKind {
    /// The input uses a feature that this binary does not support.
    Unsupported,
    /// The parse of the input exceeds the work limit.
    ParseWork,
}

impl std::fmt::Display for Refusal {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.kind {
            RefusalKind::ParseWork => write!(out, "{REFUSED}: {}", self.reason),
            RefusalKind::Unsupported => write!(
                out,
                "{REFUSED}: unsupported: {}: {}",
                self.part, self.reason
            ),
        }
    }
}

pub(crate) fn refused(part: &'static str, reason: impl Into<String>) -> Refusal {
    Refusal {
        part,
        reason: reason.into(),
        kind: RefusalKind::Unsupported,
    }
}
