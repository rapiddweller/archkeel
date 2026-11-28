// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The pool of candidates that wait for the value flow of `impl_flow` (#1942).

use std::collections::HashMap;

use crate::builder::Builder;
use crate::modules::Index;
use crate::site::Site;
use crate::type_reach_filter::Filter;

/// Compact pending candidate waiting for value-flow settlement (#1942).
pub(crate) struct Pending {
    pub(crate) source: u32,
    pub(crate) site: u32,
    pub(crate) target: u32,
    pub(crate) reason: u32,
    pub(crate) erased: bool,
    pub(crate) execution: bool,
    pub(crate) no_name_route: bool,
    /// The site of the target that a settled named candidate keeps as its execution doubt (AD-1510).
    pub(crate) home: Option<u32>,
}

/// Interned candidate pool sharing `Builder`'s string table (#1942).
pub(crate) struct PendingPool {
    pub(crate) sites: Vec<(u32, Site)>,
    site_index: HashMap<(u32, i64, i64, i64), u32>,
    pub(crate) items: Vec<Pending>,
}

impl PendingPool {
    pub(crate) fn new() -> Self {
        Self {
            sites: Vec::new(),
            site_index: HashMap::new(),
            items: Vec::new(),
        }
    }

    fn intern_site(&mut self, builder: &mut Builder, rel: &str, site: &Site) -> u32 {
        let rel_id = builder.intern_text(rel);
        let key = (rel_id, site.line, site.end_line, site.column);
        if let Some(&id) = self.site_index.get(&key) {
            return id;
        }
        let id = u32::try_from(Vec::len(&self.sites)).unwrap_or(u32::MAX);
        self.sites.push((rel_id, site.clone()));
        self.site_index.insert(key, id);
        id
    }

    pub(crate) fn push(
        &mut self,
        builder: &mut Builder,
        (source, target): (&str, &str),
        (rel, site): (&str, &Site),
        reason: &str,
        (erased, execution, no_name_route): (bool, bool, bool),
        home: Option<(&str, &Site)>,
    ) {
        let home = home.map(|(rel, site)| self.intern_site(builder, rel, site));
        let site = self.intern_site(builder, rel, site);
        self.items.push(Pending {
            source: builder.intern_text(source),
            site,
            target: builder.intern_text(target),
            reason: builder.intern_text(reason),
            erased,
            execution,
            no_name_route,
            home,
        });
    }

    /// The compiler resolved the written call of a named candidate to another module (AD-1185): the named doubt
    /// is settled. `Some(runs)` says whether an argument of the call can still run code of the target (AD-1510).
    pub(crate) fn elsewhere(
        &self,
        (builder, index): (&Builder, &Index<'_>),
        reach: Option<&Filter<'_>>,
        pending: &Pending,
    ) -> Option<bool> {
        if pending.execution {
            return None;
        }
        let (rel, site) = self.site_of(pending.site)?;
        let target = index.rel(builder.interned_text(pending.target))?;
        let at = (builder.interned_text(rel), site.line, site.column);
        Filter::resolved_elsewhere(reach, target, at)
    }

    pub(crate) fn site_of(&self, id: u32) -> Option<(u32, &Site)> {
        let (rel, site) = self.sites.get(usize::try_from(id).ok()?)?;
        Some((*rel, site))
    }
}
