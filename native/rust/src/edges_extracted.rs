// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The invariant of the extraction (AD-352, as `imports.rs` of the TypeScript collector): each
//! `use` leaf, qualified path and macro call of a file ends as a record, as a gap, or as a local
//! path that gives no edge. A second count of the tree (`scan_extracted.rs`) must equal the
//! outcomes that the edges produced (a method call ends in `method_gaps`, #953): each record, gap or local outcome adds one to
//! `Builder::ended`, and a branch that ends nothing adds nothing. A bug that drops one of them is
//! then a gap named `unextracted`, so it can never read as a complete scan.

use crate::builder::Builder;
use crate::tree::Module;

impl Builder {
    /// Compare the count of each module with the outcomes that its references and calls ended.
    pub(crate) fn check_extracted(&mut self, modules: &[Module]) {
        for module in modules {
            let tally = module.scan.tally;
            let references = self.ended_references.get(&module.rel).copied().unwrap_or(0);
            let calls = self.ended_calls.get(&module.rel).copied().unwrap_or(0);
            let methods = self.ended_methods.get(&module.rel).copied().unwrap_or(0);
            let ended = references.saturating_sub(tally.unseen)
                + calls.saturating_sub(tally.hidden)
                + methods.saturating_sub(tally.hidden_methods);
            if ended == tally.expected {
                continue;
            }
            let rel = &module.rel;
            let reason = if ended < tally.expected {
                let lost = tally.expected - ended;
                format!("unextracted: {lost} use, path or macro call node(s) of {rel} have no record and no gap")
            } else {
                let extra = ended - tally.expected;
                format!("unextracted: the scan of {rel} ended {extra} more outcome(s) than the tree has nodes")
            };
            self.gap(&reason, None, &module.module);
        }
    }
}
