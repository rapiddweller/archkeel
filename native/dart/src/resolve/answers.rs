// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed answers of the resolver for the collection (AD-400, AD-796): each directive, each
//! name that a base or a type alias writes, each site and each construction. The collection
//! asks only for these keys, and a missing key stops it (`CollectionInputGap`).
//!
//! S2 of AD-796 resolves each site and each construction (`sites.rs`, `construct.rs`).

use std::collections::BTreeSet;

use super::{class_like, Bound, Resolver};
use crate::collection::types::{
    Answers, Binding, Construction, ConstructionAnswer, DirectiveAnswer, DirectiveTarget,
    NameAnswer, ResolvedSite, SitesAnswer,
};
use crate::syntax::{
    Definition, DefinitionKind, DirectiveKind, Site, SiteKind, SiteUse, Syntax, Visibility,
};

impl Resolver<'_> {
    /// The answers for each source with a module and a full parse.
    pub(crate) fn answers(&self) -> Answers {
        let mut answers = Answers {
            directives: Vec::new(),
            names: Vec::new(),
            sites: Vec::new(),
            constructions: Vec::new(),
            problems: Vec::new(),
        };
        for at in 0..Vec::len(&self.index.kinds) {
            if let (Some(_), Some(Some(parsed))) = (self.module_for(at), self.syntax.get(at)) {
                self.file_answers(at, parsed, &mut answers);
            }
        }
        answers
    }

    fn file_answers(&self, at: usize, parsed: &Syntax, answers: &mut Answers) {
        let rel = self.rel(at).to_owned();
        let directives = parsed.directives.iter().filter(|directive| {
            matches!(
                directive.kind,
                DirectiveKind::Import | DirectiveKind::Export
            )
        });
        for directive in directives {
            let targets = self
                .targets(at, directive)
                .into_iter()
                .map(|target| DirectiveTarget {
                    module: target.module,
                    package: target.package,
                    rel_path: target.at.map(|library| self.rel(library).to_owned()),
                    uri: target.uri,
                    builtin: target.builtin,
                })
                .collect();
            answers.directives.push(DirectiveAnswer {
                rel: rel.clone(),
                start: directive.span.start_byte,
                targets,
            });
        }
        let names: BTreeSet<&str> = parsed.definitions.iter().flat_map(written_names).collect();
        for name in names {
            answers.names.push(NameAnswer {
                rel: rel.clone(),
                name: name.to_owned(),
                targets: self.resolve_name(at, name),
            });
        }
        let sites = parsed
            .sites
            .iter()
            .flat_map(|site| self.site_answers(at, site))
            .collect();
        let mut constructions = BTreeSet::new();
        let built = parsed
            .sites
            .iter()
            .filter(|site| matches!(site.kind, SiteKind::Call | SiteKind::Creation));
        for site in built {
            if constructions.insert((site.span.start_byte, String::as_str(&site.expression))) {
                answers
                    .constructions
                    .push(self.construction_answer(at, &rel, site));
            }
        }
        answers.sites.push(SitesAnswer { rel, sites });
    }
}

/// The type texts of a definition that the collection resolves: its bases, or its alias.
fn written_names(definition: &Definition) -> Vec<&str> {
    let mut names = Vec::new();
    if class_like(definition.kind) {
        let bases = definition
            .extends
            .iter()
            .chain(&definition.with_types)
            .chain(&definition.implements);
        names.extend(bases.map(String::as_str));
    }
    if definition.kind == DefinitionKind::Typedef {
        names.extend(definition.alias.as_deref());
    }
    names
}

impl Resolver<'_> {
    /// The answers of one site; a read-write reference gives a read and a write.
    fn site_answers(&self, at: usize, site: &Site) -> Vec<ResolvedSite> {
        let uses = if site.kind == SiteKind::Reference && site.r#use == SiteUse::ReadWrite {
            vec![SiteUse::Read, SiteUse::Write]
        } else {
            vec![site.r#use]
        };
        uses.into_iter()
            .map(|used| {
                let mut site = site.clone();
                site.r#use = used;
                let (status, bound) = self.site(at, &site);
                let bindings = bound.iter().map(|item| self.binding(item)).collect();
                ResolvedSite {
                    site,
                    status,
                    bindings,
                }
            })
            .collect()
    }

    fn construction_answer(&self, at: usize, rel: &str, site: &Site) -> ConstructionAnswer {
        let built = self.construction(at, site);
        ConstructionAnswer {
            rel: rel.to_owned(),
            start: site.span.start_byte,
            expression: site.expression.clone(),
            resolution: Construction {
                status: built.status,
                binding: built.bound.as_ref().map(|item| self.binding(item)),
                reason: built.reason.map(str::to_owned),
                inferred_type: self.inferred_constructor_type(at, site, &built),
            },
        }
    }

    /// The typed binding of the collection (`ResolvedBinding`).
    fn binding(&self, bound: &Bound) -> Binding {
        Binding {
            module: bound.module.clone(),
            name: bound.name.clone(),
            kind: bound.kind,
            via_prefix: bound.via_prefix.clone(),
            declaration_id: bound.id.clone(),
            rel_path: self.rel(bound.at).to_owned(),
            span: bound.span.clone(),
            visibility: Visibility::from_name(&bound.name),
        }
    }
}
