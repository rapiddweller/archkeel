// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Classify verified occurrence joins without adding project symbols.

use std::collections::{BTreeMap, BTreeSet};

use scip_serde::Serialize;

use super::syntax::{CallSite, Dispatch, Source};
use super::wire::{Occurrence, Range};

#[derive(Clone, Eq, PartialEq, Serialize)]
#[serde(crate = "scip_serde")]
struct Anchor {
    target_definition_id: String,
    evidence_id: String,
    path: String,
    line: u32,
    dispatch_kind: Dispatch,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde")]
struct Reference {
    path: String,
    start_line: u32,
    start_column: u32,
    end_line: u32,
    end_column: u32,
}

impl Reference {
    fn at(path: &str, range: Range) -> Self {
        let [start_line, start_column, end_line, end_column] = range.0;
        Self {
            path: path.to_owned(),
            start_line,
            start_column,
            end_line,
            end_column,
        }
    }
}

#[derive(Serialize)]
#[serde(crate = "scip_serde")]
pub(super) struct Binding<'a> {
    call_id: &'a str,
    #[serde(flatten)]
    resolution: Resolution<'a>,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde", rename_all = "snake_case")]
enum Provenance {
    AstExact,
    ScipVerified,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde", rename_all = "snake_case")]
enum Reason {
    MacroCall,
    UnmappedScipRef,
    NoScipRef,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde", tag = "status", rename_all = "snake_case")]
enum Resolution<'a> {
    LocalResolved {
        provenance: Provenance,
        reference: &'a Reference,
        #[serde(flatten)]
        anchor: &'a Anchor,
    },
    Unresolved {
        provenance: Option<Provenance>,
        #[serde(skip_serializing_if = "Option::is_none")]
        reference: Option<&'a Reference>,
        reason: Reason,
    },
    #[serde(untagged)]
    External {
        status: ExternalKind,
        provenance: Provenance,
        reference: &'a Reference,
        #[serde(flatten)]
        symbol: External<'a>,
    },
}

#[derive(Serialize)]
#[serde(crate = "scip_serde", rename_all = "snake_case")]
enum ExternalKind {
    ExternalStd,
    ExternalDep,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde")]
struct External<'a> {
    crate_name: &'a str,
    crate_version: Option<&'a str>,
    symbol_path: &'a str,
}

impl<'a> External<'a> {
    fn from_symbol(symbol: &'a str) -> Option<Self> {
        let mut fields = symbol.splitn(5, ' ');
        let scheme = fields.next()?;
        let manager = fields.next()?;
        let name = fields.next()?;
        let version = fields.next()?;
        let path = fields.next()?;
        if scheme.is_empty()
            || manager.is_empty()
            || name.is_empty()
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
            || version.is_empty()
            || path.trim().is_empty()
        {
            return None;
        }
        Some(Self {
            crate_name: name,
            crate_version: (version != ".").then_some(version),
            symbol_path: path,
        })
    }
}

#[derive(Default)]
pub(super) struct Matches<'a> {
    packages: BTreeSet<String>,
    targets: BTreeMap<String, Option<Anchor>>,
    references: BTreeMap<&'a str, (Reference, Option<String>)>,
}

impl<'a> Matches<'a> {
    pub(super) fn local_packages(&mut self, names: Vec<String>) {
        self.packages
            .extend(names.into_iter().map(|name| normalize(&name)));
    }

    pub(super) fn occurrence(
        &mut self,
        path: &str,
        occurrence: Occurrence<'_>,
        anchors: &Source<'a>,
    ) {
        let Some(range) = occurrence.range else {
            return;
        };
        if occurrence.symbol.is_empty() {
            return;
        }
        if occurrence.definition {
            self.definition(path, range, occurrence.symbol, anchors);
        } else if let Some(id) = occurrence
            .reference
            .then_some(range)
            .and_then(|range| anchors.calls.get(&range))
            .filter(|ids| ids.len() == 1)
            .and_then(BTreeSet::first)
        {
            let symbol = String::from(occurrence.symbol);
            self.references
                .entry(id)
                .and_modify(|(_, prior)| *prior = prior.take().filter(|current| current == &symbol))
                .or_insert_with(|| (Reference::at(path, range), Some(symbol)));
        }
    }

    fn definition(&mut self, path: &str, range: Range, symbol: &str, anchors: &Source<'a>) {
        if symbol.starts_with("local ") {
            return;
        }
        if let Some(package) = External::from_symbol(symbol) {
            self.packages.insert(normalize(package.crate_name));
        }
        let found = anchors
            .definitions
            .get(&range)
            .map(|(id, evidence, dispatch)| Anchor {
                target_definition_id: (*id).to_owned(),
                evidence_id: evidence.clone(),
                path: path.to_owned(),
                line: range.0[0].saturating_add(1),
                dispatch_kind: *dispatch,
            });
        record(&mut self.targets, symbol.to_owned(), found);
    }

    pub(super) fn bind(&self, call: &'a CallSite) -> Binding<'_> {
        let resolution = if call.macro_call {
            Resolution::Unresolved {
                provenance: Some(Provenance::AstExact),
                reference: None,
                reason: Reason::MacroCall,
            }
        } else if let Some((site, symbol)) = self.references.get(call.id.as_str()) {
            self.reference_resolution(site, symbol.as_deref())
        } else {
            Resolution::Unresolved {
                provenance: None,
                reference: None,
                reason: Reason::NoScipRef,
            }
        };
        Binding {
            call_id: &call.id,
            resolution,
        }
    }

    fn reference_resolution<'r>(
        &'r self,
        site: &'r Reference,
        symbol: Option<&'r str>,
    ) -> Resolution<'r> {
        let provenance = Provenance::ScipVerified;
        if let Some(needle) = symbol {
            if let Some(Some(anchor)) = self.targets.get(needle) {
                return Resolution::LocalResolved {
                    provenance,
                    reference: site,
                    anchor,
                };
            }
            if let Some((status, symbol)) = self.external(needle) {
                return Resolution::External {
                    status,
                    provenance,
                    reference: site,
                    symbol,
                };
            }
        }
        Resolution::Unresolved {
            provenance: Some(provenance),
            reference: Some(site),
            reason: Reason::UnmappedScipRef,
        }
    }

    fn external<'s>(&self, symbol: &'s str) -> Option<(ExternalKind, External<'s>)> {
        let found = External::from_symbol(symbol)?;
        if self.targets.contains_key(symbol) || self.packages.contains(&normalize(found.crate_name))
        {
            return None;
        }
        let status = if matches!(found.crate_name, "core" | "alloc" | "std") {
            ExternalKind::ExternalStd
        } else {
            ExternalKind::ExternalDep
        };
        Some((status, found))
    }
}

fn normalize(name: &str) -> String {
    name.replace('-', "_")
}

pub(super) fn record<K: Ord, T: Eq>(map: &mut BTreeMap<K, Option<T>>, key: K, value: Option<T>) {
    map.entry(key)
        .and_modify(|prior| {
            if *prior != value {
                *prior = None;
            }
        })
        .or_insert(value);
}
