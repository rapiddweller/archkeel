// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Binding targets and earliest sites do not change during one immutable lexical index.

use super::*;

impl Index<'_> {
    pub(super) fn summarize(&mut self, scan: &mut Scan) -> Result<()> {
        for id in 0..self.scopes.len() {
            scan.tick(1)?;
            let summaries = self.scope_summaries(scan, id)?;
            self.scope_mut(id)?.summaries = summaries;
        }
        Ok(())
    }

    fn scope_summaries(&self, scan: &mut Scan, id: usize) -> Result<BTreeMap<String, Summary>> {
        let scope = self.scope(id)?;
        let mut summaries = BTreeMap::new();
        for (name, sites) in &scope.bindings {
            scan.tick(1)?;
            summaries.insert(
                name.clone(),
                self.summarize_binding(scan, scope, name, sites)?,
            );
        }
        Ok(summaries)
    }

    fn summarize_binding(
        &self,
        scan: &mut Scan,
        scope: &Scope<'_>,
        name: &str,
        sites: &[Site<'_>],
    ) -> Result<Summary> {
        let mut targets = BTreeSet::new();
        let mut kinds = BTreeSet::new();
        let mut conditional = false;
        let mut earliest = None;
        for site in sites {
            scan.tick(1)?;
            conditional |= site.conditional;
            let (_, line, _, column) = self
                .located_site(&site.node)
                .ok_or("binding site location unseen")?;
            earliest =
                Some(earliest.map_or((line, column), |at: (i64, i64)| at.min((line, column))));
            if let Some((target, kind)) = self.target(scan, scope, site, name)? {
                targets.insert(target);
                kinds.insert(kind);
            }
        }
        let kind = if targets.is_empty() {
            "local"
        } else if kinds.len() == 1 {
            kinds.first().map_or("mixed", String::as_str)
        } else {
            "mixed"
        };
        let uncertain =
            sites.len() != 1 || conditional || !targets.is_empty() && targets.len() != 1;
        scan.tick(targets.len())?;
        Ok(Summary {
            targets: targets.into_iter().collect(),
            kind: kind.into(),
            uncertain,
            earliest,
        })
    }

    fn target(
        &self,
        scan: &mut Scan,
        scope: &Scope<'_>,
        site: &Site<'_>,
        name: &str,
    ) -> Result<Option<(String, String)>> {
        let declaration = match &site.node {
            Node::Stmt(Stmt::FunctionDef(n)) => Some(n.name.as_str()),
            Node::Stmt(Stmt::ClassDef(n)) => Some(n.name.as_str()),
            _ => None,
        };
        if let Some(name) = declaration {
            return Ok(Some((
                scan.owner(&scope.qualified, name)?.to_string(),
                "declaration".into(),
            )));
        }
        if !matches!(site.node, Node::Stmt(Stmt::Import(_) | Stmt::ImportFrom(_))) {
            return Ok(None);
        }
        let (_, line, _, column) = self
            .located_site(&site.node)
            .ok_or("import site location unseen")?;
        let Some((target, kind)) = self.aliases.get(&(line, column, name.to_owned())) else {
            return Ok(None);
        };
        scan.tick(target.len())?;
        Ok(Some((target.clone(), kind.clone())))
    }
}
