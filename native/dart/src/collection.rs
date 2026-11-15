// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The complete raw collection assembly; resolution remains a typed input (AD-400).

mod builder;
mod imports;
mod inventories;
mod prepare;
mod sites;
mod targets;
pub(crate) mod types;

use crate::declarations::types as decl;
use crate::declarations::work::Stop;
use archkeel_facts::envelope::{Capabilities, FileFact, SectionName};
use archkeel_facts::vocab::ExceptionName;
use builder::{file_span, Builder};
use types::{Input, Output, Source};

const SECTIONS: [SectionName; 6] = [
    SectionName::Imports,
    SectionName::Unknowns,
    SectionName::Symbols,
    SectionName::Calls,
    SectionName::References,
    SectionName::Bindings,
];

pub(crate) fn build(input: &Input) -> Output {
    let mut builder = Builder::new(input);
    if let Err(stop) = builder.run() {
        let message = match stop {
            Stop::Input => {
                "CollectionInputGap: Dart collection resolver inputs are incomplete or inconsistent"
            }
            Stop::Work => "CollectionWorkLimit: Dart collection assembly passes the work limit",
        };
        let (_, gap) =
            crate::records::gap(".", 1, ExceptionName::UnsupportedDeclaration, message, None);
        return Output {
            gaps: vec![gap],
            work: builder.decl.work.spent(),
            ..Output::default()
        };
    }
    builder.finish()
}

impl<'a> Builder<'a> {
    fn run(&mut self) -> Result<(), Stop> {
        self.decl.work.input(self.input)?;
        self.prepare()?;
        self.index_answers()?;
        let mut files = Vec::new();
        for file in &self.files {
            self.decl.work.copies(file)?;
            if self.parsed.contains(&file.rel) {
                files.push(file.clone());
            }
        }
        self.decl.run(&decl::Input { files })?;
        for (index, scope) in self.decl.output.scope_candidates.iter().enumerate() {
            self.decl.work.copies(scope)?;
            self.scopes
                .entry((scope.0.clone(), None))
                .or_default()
                .push(index);
            self.scopes
                .entry((scope.0.clone(), Some(scope.1.clone())))
                .or_default()
                .push(index);
        }
        for (index, symbol) in self.decl.output.symbols.iter().enumerate() {
            self.decl.work.text(&symbol.data.qualified_name)?;
            self.symbol_indices
                .insert(symbol.data.qualified_name.clone(), index);
        }
        self.for_parsed_file(Self::imports)?;
        self.for_parsed_file(Self::bases)?;
        self.for_parsed_file(Self::sites)?;
        self.duplicates()?;
        for problem in &self.input.resolver.problems {
            self.decl.work.copies(problem)?;
            self.gap(
                &problem.path,
                problem.span.as_ref().unwrap_or(&file_span()),
                problem.kind,
                &problem.message,
                None,
            )?;
        }
        self.finalize_inventories()?;
        self.source_facts()?;
        for symbol in &self.decl.output.symbols {
            self.decl.work.text(symbol.id.as_str())?;
        }
        for record in self.output.calls.iter().chain(&self.output.references) {
            self.decl.work.text(record.id.as_str())?;
        }
        for record in &self.output.imports {
            self.decl.work.text(record.id.as_str())?;
        }
        Ok(())
    }

    fn index_answers(&mut self) -> Result<(), Stop> {
        for (index, answer) in self.input.resolver.directives.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .directive_indices
                .insert((answer.rel.clone(), answer.start), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.names.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .name_indices
                .insert((answer.rel.clone(), answer.name.clone()), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.sites.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .site_indices
                .insert(answer.rel.clone(), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.constructions.iter().enumerate() {
            self.decl.work.copies(answer)?;
            let key = (answer.rel.clone(), answer.start, answer.expression.clone());
            if self.construction_indices.insert(key, index).is_some() {
                return Err(Stop::Input);
            }
        }
        Ok(())
    }

    fn for_parsed_file(
        &mut self,
        collect: fn(&mut Self, &'a Source) -> Result<(), Stop>,
    ) -> Result<(), Stop> {
        for source in &self.input.files {
            self.decl.work.charge(1)?;
            if self.parsed.contains(&source.file.rel) {
                collect(self, source)?;
            }
        }
        Ok(())
    }

    fn source_facts(&mut self) -> Result<(), Stop> {
        for rel in &self.parsed {
            self.decl.work.charge(1)?;
            let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
            let source = self.input.files.get(index).ok_or(Stop::Input)?;
            let file = self.files.get(index).ok_or(Stop::Input)?;
            if file.module != source.file.module {
                continue;
            }
            self.decl.work.text(&source.content)?;
            let evidence = self.decl.gap_cite(file, &file_span());
            self.output.files.push(FileFact::of(
                (rel, &file.module),
                crate::pytext::is_blank(source.content.as_bytes()),
                evidence,
            ));
        }
        self.decl.work.copies(&self.input.inputs)?;
        self.output.inputs = self.input.inputs.clone();
        self.output.source_digest = crate::records::listing_digest(&self.output.inputs);
        self.output.scope = self
            .input
            .roots
            .iter()
            .map(|root| crate::records::pattern(root))
            .collect();
        self.output.git_head.clone_from(&self.input.git_head);
        self.output.dirty = Some(self.input.dirty.clone());
        self.output.capabilities = Some(Capabilities {
            constructs: Vec::new(),
            resolution_features: vec!["inner-uml-v1".to_owned()],
            sections: SECTIONS.to_vec(),
        });
        self.output.selected_files = self.by_path.keys().cloned().collect();
        self.output.files_read = self.files.len();
        self.output.files_parsed = self.parsed.len();
        self.output.full_scope = self.decl.gaps.is_empty() && !self.files.is_empty();
        Ok(())
    }

    fn finish(mut self) -> Output {
        self.output.symbols = self.decl.output.symbols;
        self.output.symbols.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.imports.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.calls.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.references.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.gaps = self.decl.gaps.into_values().collect();
        self.output.evidence = self.decl.evidence.into_values().collect();
        self.output.work = self.decl.work.spent();
        self.output
    }
}
