// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One import record for each reference, with its target (`collect._references` and below).
//!
//! A reference that cannot be proven is an UNKNOWN gap, never a PASS: a computed specifier, a
//! setting that is not observed, a target that no rule covers.

use super::{Collection, GapKind};
use crate::kept::Kept;
use crate::kept_script::ScriptFile;
use crate::manifest::Lookup;
use crate::options::ModuleKind;
use crate::parse::{parse_for, Parsed};
use crate::plant;
use crate::references::Form;
use crate::source_input::{classify_file, ModuleFormat, SourceKind};

impl Collection<'_> {
    /// Parse a file, report what it cannot prove, and record each of its references.
    pub(super) fn references(&mut self, rel: &str, module: &str, file_evidence: &str, text: &str) {
        let reach = self.resolver.options.reach();
        let mut parsed = parse_for(
            &mut self.parsers,
            rel,
            text.as_bytes(),
            reach,
            archkeel_snapshot::work::depth_limit(),
        );
        if parsed.depth_limited {
            archkeel_snapshot::work::refuse_depth(rel);
            return;
        }
        if let Some(line) = parsed.first_error {
            let reason = format!("Syntax error in {rel}: unparseable construct at line {line}");
            self.gap(&reason, Some(file_evidence), module, GapKind::Collection);
        }
        for concern in &parsed.concerns {
            let evidence = self.cite(rel, &concern.span);
            self.gap(
                &concern.reason,
                Some(&evidence),
                module,
                GapKind::Collection,
            );
        }
        let format = self.resolver.format_of(&mut self.snapshot, rel);
        let explicit = self.resolver.options.module;
        // `collect._global_dependency_scope`: a file that is neither a declaration nor CommonJS.
        let suffix = classify_file(rel);
        let global_scope = suffix.is_some_and(|suffix| {
            suffix.source_kind() != Some(SourceKind::Declaration)
                && suffix.format_hint() != Some(ModuleFormat::Cjs)
        }) && matches!(format, Lookup::Missing | Lookup::Hit(ModuleFormat::Esm));
        let format_known = !matches!(format, Lookup::Missing);
        let script = ScriptFile::take(&mut parsed, format_known, global_scope);
        self.script_file_effects(rel, module, &script);
        let kept = Kept::from_parsed(module, &mut parsed, text, script);
        self.order.push(rel.to_owned());
        self.kept.insert(rel.to_owned(), kept);
        let cjs = suffix.and_then(|suffix| suffix.format_hint()) == Some(ModuleFormat::Cjs)
            || explicit == Some(ModuleKind::CommonJs)
            || (format == Lookup::Hit(ModuleFormat::Cjs)
                && matches!(explicit, Some(ModuleKind::NodeNext | ModuleKind::Node16)));
        let mut handled = 0usize;
        for (index, reference) in parsed.references.iter().enumerate() {
            if plant::skip(rel, index) {
                continue;
            }
            let evidence = self.cite(rel, &reference.span);
            if reference.form == Form::Require && (!cjs || parsed.shadows_require) {
                let reason = "Unproven or shadowed require call";
                self.gap(reason, Some(&evidence), module, GapKind::Resolution);
            } else if reference.specifier.is_none() {
                let reason = format!("Computed {} cannot be resolved", reference.form.as_str());
                self.gap(&reason, Some(&evidence), module, GapKind::Resolution);
            } else {
                self.import(rel, module, reference, &evidence, &format);
            }
            handled += 1;
        }
        self.check_extracted(&parsed, handled, (rel, module, file_evidence));
    }

    /// The invariant of the extraction: each import-bearing node of the tree has a record or a gap.
    /// A node in a repaired part of the file has the gap of the syntax error. Any other node that
    /// has neither is a gap of its own, so a node that the extraction lost can never read as a
    /// complete scan.
    fn check_extracted(&mut self, parsed: &Parsed, handled: usize, file: (&str, &str, &str)) {
        let (rel, module, evidence) = file;
        let lost = parsed.places.saturating_sub(handled);
        if lost > 0 && parsed.first_error.is_none() {
            let reason = format!(
                "unextracted: {lost} import-bearing node(s) of {rel} have no record and no gap"
            );
            self.gap(&reason, Some(evidence), module, GapKind::Collection);
        }
    }
}
