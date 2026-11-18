// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

/// A proved method call outside its allowed scope.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CallOwnerViolation {
    /// The violation id.
    pub id: String,
    /// The rule that forbids the call.
    pub rule: String,
    /// The call fact that proves the violation.
    pub fact_id: String,
    /// The lexical scope of the call.
    pub source: String,
    /// The exact invoked method.
    pub target: String,
    /// The source evidence of the call and its binding.
    pub evidence: Vec<String>,
}
