// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One import record for each reference, with its target (`collect._references` and below).
//!
//! A reference that cannot be proven is an UNKNOWN gap, never a PASS: a computed specifier, a
//! setting that is not observed, a target that no rule covers.

use crate::collection::{Collection, GapKind};
use crate::installed::in_node_modules;
use crate::kept::Kept;
use crate::kept_script::ScriptFile;
use crate::manifest::Lookup;
use crate::options::ModuleKind;
use crate::parse::{parse_for, Parsed};
use crate::references::{Form, Reference};
use crate::resolve::format_of;
use crate::source_input::{classify_file, classify_specifier, ModuleFormat, SourceKind};

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
        let format = format_of(&mut self.resolver, &mut self.snapshot, rel);
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
            if planted_skip(rel, index) {
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
        self.type_directives(&parsed, (rel, module), &format);
    }

    /// A leading `/// <reference types="name" />` that the compiler honors (#686). The compiler
    /// reads the type package: first `@types/<name>`, then the package `name`. It is a type-only edge
    /// to the first one that the resolver proves in `node_modules`. Any other result is the gap
    /// "Unresolved triple-slash types reference": no package installed, a name that reaches a
    /// project file, a builtin, a `resolution-mode`, an unknown module format or a blocked option.
    /// (A directive after the first statement is not honored and never reaches here.)
    fn type_directives(
        &mut self,
        parsed: &Parsed,
        file: (&str, &str),
        format: &Lookup<ModuleFormat>,
    ) {
        let (rel, module) = file;
        for reference in &parsed.directives {
            if self.types_edge(rel, module, reference, format) {
                continue;
            }
            let name = reference.specifier.as_deref().unwrap_or("");
            let evidence = self.cite(rel, &reference.span);
            let reason = format!("Unresolved triple-slash types reference: {name}");
            self.gap(&reason, Some(&evidence), module, GapKind::Resolution);
        }
    }

    /// Record the edge of a `types` directive when the resolver proves a package; else `false`.
    fn types_edge(
        &mut self,
        rel: &str,
        module: &str,
        reference: &Reference,
        format: &Lookup<ModuleFormat>,
    ) -> bool {
        let name = reference.specifier.as_deref().unwrap_or("");
        let mode = match format {
            Lookup::Hit(format) => Some(*format),
            Lookup::Missing => None,
            Lookup::Unknown(_) => return false,
        };
        let rooted = self.resolver.options.type_roots_set;
        if name.is_empty() || rooted || reference.mode_override || self.resolver.blocked.is_some() {
            return false;
        }
        let mangled = name
            .strip_prefix('@')
            .map_or_else(|| name.to_owned(), |scoped| scoped.replacen('/', "__", 1));
        for specifier in [format!("@types/{mangled}"), name.to_owned()] {
            let class = classify_specifier(&specifier);
            if !class.npm_package() || class.builtin() {
                continue;
            }
            let found = self.resolver.resolve_classified(
                &mut self.snapshot,
                (&specifier, &class),
                rel,
                mode,
                false,
            );
            let found = match found {
                Lookup::Hit(found) => found,
                Lookup::Missing => continue,
                // A candidate that the resolver cannot decide may be the one that the compiler
                // picks: never fall through to the next one.
                Lookup::Unknown(_) => return false,
            };
            let declaration = classify_file(&found.path).and_then(|suffix| suffix.source_kind())
                == Some(SourceKind::Declaration);
            if !(found.external && in_node_modules(&found.path) && declaration) {
                return false;
            }
            let evidence = self.cite(rel, &reference.span);
            let edge = Reference {
                specifier: Some(specifier),
                ..reference.clone()
            };
            self.import(rel, module, &edge, &evidence, format);
            return true;
        }
        false
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

/// Whether the dump build skips reference `index` of `rel`, as the `ARCHKEEL_PLANT_SKIP` setting
/// `rel:index` asks. The normal build never skips.
#[cfg(feature = "dump")]
fn planted_skip(rel: &str, index: usize) -> bool {
    std::env::var("ARCHKEEL_PLANT_SKIP").is_ok_and(|planted| planted == format!("{rel}:{index}"))
}

/// The normal build never skips a reference.
#[cfg(not(feature = "dump"))]
fn planted_skip(_rel: &str, _index: usize) -> bool {
    false
}
