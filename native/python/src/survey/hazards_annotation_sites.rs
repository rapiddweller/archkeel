// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites of the closed-binding rule for the modules of a scan (AD-1175).

use ruff_text_size::TextRange;

use super::super::trojan_horse::Site;
use super::entity::{Entity, Project, BUDGET, BUILDERS};
use super::forms::last;
use crate::module::Module;
use crate::survey::hazards_names::DYNAMIC;

/// The sites of the closed-binding rule for each module of the scan, in the order of `modules`.
pub(in crate::survey) fn annotation_sites(modules: &[Module]) -> Vec<Vec<Site>> {
    let project = Project::of(modules);
    (0..modules.len()).map(|at| project.sites(at)).collect()
}

impl<'a> Project<'a> {
    /// The sites of the rule for one module; none when it evaluates no annotation.
    fn sites(&self, at: usize) -> Vec<Site> {
        let facts = self.facts(at);
        if !facts.evaluates {
            return Vec::new();
        }
        self.budget.set(BUDGET);
        let mut found = Vec::new();
        let mut add = |detail: &str, range: TextRange| {
            found.push(Site::plain(DYNAMIC, detail, range));
        };
        facts
            .reaches
            .iter()
            .for_each(|r| add("__annotations__", *r));
        for call in &facts.calls {
            let real = match self.path(call.callee, at, call.scope, 0, &mut Vec::new()) {
                Entity::Standard(path) => path.rsplit('.').next().unwrap_or_default().to_owned(),
                _ => String::new(),
            };
            let spelled = last(call.callee).unwrap_or_default();
            let named = |name: &str| real == name || spelled == name;
            let read = call.literal_ref && spelled == "ForwardRef";
            if BUILDERS.iter().any(|b| named(b)) || (named("ForwardRef") && !read) {
                add("annotation builder", call.range);
            }
        }
        let mut ranges = Vec::new();
        for (expr, scope) in &facts.annotations {
            self.dynamic(expr, (at, *scope), &mut ranges, 0, &mut Vec::new());
        }
        ranges.iter().for_each(|r| add("annotation value", *r));
        found.sort_by_key(|site| site.range.start());
        found
    }
}
