// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed answers of the resolver for the collection (AD-400, AD-796): each directive, each
//! name that a base or a type alias writes, each site and each construction. The collection
//! asks only for these keys, and a missing key stops it (`CollectionInputGap`).
//!
//! S1 of AD-796 resolves the directives and the names. It gives no site a binding: each site and
//! each construction is `unknown`, and the reply writes no call and no reference section.

use std::collections::BTreeSet;

use super::{class_like, Resolver};
use crate::collection::types::{
    Answers, Construction, ConstructionAnswer, DirectiveAnswer, DirectiveTarget, NameAnswer,
    Resolution, ResolvedSite, SitesAnswer,
};
use crate::syntax::{Definition, DefinitionKind, DirectiveKind, Site, SiteKind, SiteUse, Syntax};

/// Why a site of S1 has no binding.
const UNREAD: &str = "the resolver does not read sites yet (AD-796 S1)";

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
        let sites = parsed.sites.iter().flat_map(unread_sites).collect();
        let mut constructions = BTreeSet::new();
        for site in parsed
            .sites
            .iter()
            .filter(|site| matches!(site.kind, SiteKind::Call | SiteKind::Creation))
        {
            if constructions.insert((site.span.start_byte, String::as_str(&site.expression))) {
                answers.constructions.push(unread_construction(&rel, site));
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

/// The answers of one site without a binding; a read-write reference gives a read and a write.
fn unread_sites(site: &Site) -> Vec<ResolvedSite> {
    let uses = if site.kind == SiteKind::Reference && site.r#use == SiteUse::ReadWrite {
        vec![SiteUse::Read, SiteUse::Write]
    } else {
        vec![site.r#use]
    };
    uses.into_iter()
        .map(|used| {
            let mut site = site.clone();
            site.r#use = used;
            ResolvedSite {
                site,
                status: Resolution::Unknown,
                bindings: Vec::new(),
            }
        })
        .collect()
}

fn unread_construction(rel: &str, site: &Site) -> ConstructionAnswer {
    ConstructionAnswer {
        rel: rel.to_owned(),
        start: site.span.start_byte,
        expression: site.expression.clone(),
        resolution: Construction {
            status: Resolution::Unknown,
            binding: None,
            reason: Some(UNREAD.to_owned()),
        },
    }
}
