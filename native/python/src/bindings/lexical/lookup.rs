// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Name ownership, binding records and the complete lexical dump projection.

use super::*;

impl<'a> Index<'a> {
    pub(super) fn bind(&mut self, scan: &mut Scan) -> Result<()> {
        for scope in &mut self.scopes {
            scan.tick(1)?;
            for name in scope.globals.iter().chain(&scope.nonlocals) {
                scan.tick(1)?;
                scope.locals.remove(name);
            }
        }
        for id in (1..self.scopes.len()).rev() {
            scan.tick(1)?;
            self.propagate(scan, id)?;
        }
        self.inline_locals(scan)?;
        for (scope, name, site) in std::mem::take(&mut self.sites) {
            scan.tick(1)?;
            if let Some(owner) = self.owner(scan, scope, &name)? {
                self.scope_mut(owner)?
                    .bindings
                    .entry(name)
                    .or_default()
                    .push(site);
            }
        }
        self.summarize(scan)
    }

    fn inline_locals(&mut self, scan: &mut Scan) -> Result<()> {
        for id in std::mem::take(&mut self.inline_scopes) {
            scan.tick(1)?;
            self.inline_scope_locals(scan, id)?;
        }
        Ok(())
    }

    fn inline_scope_locals(&mut self, scan: &mut Scan, id: usize) -> Result<()> {
        let parent = self
            .scope(id)?
            .compiler_parent
            .ok_or("inlined compiler owner unseen")?;
        scan.tick(self.scope(id)?.locals.len())?;
        let names: Vec<_> = self.scope(id)?.locals.iter().cloned().collect();
        for name in names {
            scan.tick(1)?;
            let scope = self.scope_mut(parent)?;
            if !scope.seen.contains(&name)
                && !scope.globals.contains(&name)
                && !scope.nonlocals.contains(&name)
            {
                scope.compiler_locals.insert(name);
            }
        }
        Ok(())
    }

    fn propagate(&mut self, scan: &mut Scan, id: usize) -> Result<()> {
        scan.tick(self.scope(id)?.seen.len())?;
        let names: Vec<_> = self.scope(id)?.seen.iter().cloned().collect();
        for name in names {
            scan.tick(1)?;
            if self.scope(id)?.locals.contains(&name) || self.scope(id)?.globals.contains(&name) {
                continue;
            }
            self.propagate_name(scan, id, &name)?;
        }
        Ok(())
    }

    fn propagate_name(&mut self, scan: &mut Scan, id: usize, name: &str) -> Result<()> {
        let mut parent = self.scope(id)?.parent;
        let mut crossed = Vec::new();
        let mut found = false;
        while let Some(p) = parent {
            scan.tick(1)?;
            let scope = self.scope(p)?;
            if scope.globals.contains(name) {
                break;
            }
            if scope.kind != Kind::Class && scope.locals.contains(name) {
                found = true;
                break;
            }
            crossed.push(p);
            parent = scope.parent;
        }
        if found {
            for p in crossed {
                scan.tick(1)?;
                self.scope_mut(p)?.seen.insert(name.into());
            }
        }
        Ok(())
    }

    fn owner(&self, scan: &mut Scan, id: usize, name: &str) -> Result<Option<usize>> {
        let scope = self.scope(id)?;
        if scope.blocked.contains(name) {
            return Ok(None);
        }
        if scope.inlined {
            return self.inlined_owner(scan, id, name);
        }
        if !scope.table {
            return Ok(None);
        }
        // The compiler stores the mangled spelling; source-spelling lookup raises KeyError.
        if scope.private_context && name.starts_with("__") && !name.ends_with("__") {
            return Ok(Some(0));
        }
        if id == 0 || scope.locals.contains(name) || scope.compiler_locals.contains(name) {
            return Ok(Some(id));
        }
        if scope.globals.contains(name) || !scope.seen.contains(name) {
            return Ok(Some(0));
        }
        self.free_owner(scan, scope.parent, name)
    }

    fn inlined_owner(&self, scan: &mut Scan, id: usize, name: &str) -> Result<Option<usize>> {
        let scope = self.scope(id)?;
        if scope.locals.contains(name) {
            return Ok(Some(id));
        }
        let mut parent = scope.parent;
        while let Some(p) = parent {
            scan.tick(1)?;
            let scope = self.scope(p)?;
            if scope.inlined && scope.locals.contains(name) {
                return Ok(Some(p));
            }
            if !scope.inlined && scope.kind != Kind::Class {
                return self.owner(scan, p, name);
            }
            parent = scope.parent;
        }
        Ok(None)
    }

    fn free_owner(
        &self,
        scan: &mut Scan,
        mut parent: Option<usize>,
        name: &str,
    ) -> Result<Option<usize>> {
        while let Some(p) = parent {
            scan.tick(1)?;
            let scope = self.scope(p)?;
            parent = scope.parent;
            if scope.inlined && scope.locals.contains(name) {
                return Ok(Some(p));
            }
            if scope.inlined {
                continue;
            }
            if !scope.table || matches!(scope.kind, Kind::Parameters | Kind::Alias) {
                return Ok(None);
            }
            if scope.globals.contains(name) {
                return Ok(Some(0));
            }
            if matches!(scope.kind, Kind::Function | Kind::Comprehension)
                && scope.locals.contains(name)
            {
                return Ok(Some(p));
            }
        }
        Ok(Some(0))
    }

    fn binding_at(
        &self,
        scan: &mut Scan,
        owner: Option<usize>,
        at: (i64, i64),
        name: &str,
    ) -> Result<Value> {
        let Some(id) = owner else {
            return Ok(json!({"owner":null,"targets":[],"kind":"unknown","uncertain":false}));
        };
        let scope = self.scope(id)?;
        let summary = scope.summaries.get(name);
        if scope.kind == Kind::Class
            && summary
                .and_then(|s| s.earliest)
                .is_some_and(|first| first > at)
        {
            return self.binding_at(scan, Some(0), at, name);
        }
        let targets = summary.map_or(&[][..], |s| s.targets.as_slice());
        let kind = if let Some(summary) = summary {
            summary.kind.as_str()
        } else if id != 0 {
            "local"
        } else if scope.bindings.contains_key("*") {
            "unknown"
        } else {
            "unbound"
        };
        let uncertain = summary.map_or(id != 0, |s| s.uncertain);
        scan.tick(targets.len())?;
        Ok(
            json!({"owner":id,"targets":targets,"kind":kind,"uncertain":uncertain}),
        )
    }

    fn receiver(&self, owner: Option<usize>, name: &str) -> Result<Option<&str>> {
        let Some(owner) = owner else {
            return Ok(None);
        };
        let scope = self.scope(owner)?;
        let Some(Node::Stmt(Stmt::FunctionDef(n))) = &scope.node else {
            return Ok(None);
        };
        let Some(parent) = scope.parent else {
            return Ok(None);
        };
        let parent = self.scope(parent)?;
        let first = n
            .parameters
            .posonlyargs
            .first()
            .or_else(|| n.parameters.args.first());
        if parent.kind == Kind::Class
            && first.is_some_and(|p| p.parameter.name.as_str() == name)
            && scope.bindings.get(name).is_some_and(|s| s.len() == 1)
            && n.decorator_list.is_empty()
        {
            return Ok(Some(&parent.qualified));
        }
        Ok(None)
    }

    pub(super) fn located_site(&self, node: &Node<'_>) -> Option<SiteKey> {
        let range = match node {
            Node::Stmt(Stmt::FunctionDef(n)) => Some(Def::Function(n).range(self.module.text())),
            Node::Stmt(Stmt::ClassDef(n)) => Some(Def::Class(n).range(self.module.text())),
            Node::Stmt(n) => Some(n.range()),
            Node::Expr(n) => Some(self.expression_range(n)),
            Node::Arg(n) => Some(TextRange::new(n.name.start(), n.end())),
            Node::Handler(n) => Some(n.range()),
            Node::Pattern(n) => Some(n.range()),
            Node::Keyword(n) => Some(n.range()),
            Node::Elif(clauses) => clauses
                .first()
                .zip(clauses.last())
                .map(|(first, last)| TextRange::new(first.start(), last.end())),
            _ => None,
        };
        let loc = self.module.location(&range?);
        Some((node.kind(), loc.line, loc.end_line, loc.column))
    }

    fn site(&self, node: &Node<'_>) -> SiteKey {
        self.located_site(node).unwrap_or((node.kind(), 1, 1, 0))
    }

    fn scope_row(&self, scan: &mut Scan, scope: &Scope<'_>) -> Result<Value> {
        let mut bindings = BTreeMap::new();
        for (name, sites) in &scope.bindings {
            scan.tick(1)?;
            let mut rows = Vec::new();
            for site in sites {
                scan.tick(1)?;
                rows.push(self.site(&site.node));
            }
            bindings.insert(name, rows);
        }
        let parent = scope.parent;
        Ok(
            json!({"qualified_name":scope.qualified.as_ref(),"definition_id":scope.identity,"parent":parent,
            "table":scope.table,"inlined":scope.inlined,"local_names":if scope.inlined {json!(scope.locals)} else {json!([])},
            "blocked_names":scope.blocked,"bindings":bindings,"node":scope.node.as_ref().map(|n|self.site(n)).unwrap_or(("Module",1,1,0))}),
        )
    }

    pub(super) fn dump(&self, scan: &mut Scan, input: &Value) -> Result<Value> {
        let mut ordered = Vec::new();
        for (id, scope) in self.scopes.iter().enumerate() {
            scan.tick(1)?;
            if id != 0 && !self.touched.contains(&id) {
                continue;
            }
            let row = self.scope_row(scan, scope)?;
            scan.output.value(&row)?;
            ordered.push((id,row));
        }
        ordered.sort_by(|a,b|scope_key(&a.1).cmp(&scope_key(&b.1)));
        scan.tick(ordered.len())?;
        let references:HashMap<usize,usize>=ordered.iter().enumerate().map(|(index,(id,_))|(*id,index)).collect();
        let mut scopes=Vec::new();
        for (_,mut row) in ordered {
            scan.tick(1)?;
            remap(&mut row,"parent",&references)?;
            scopes.push(row);
        }
        let mut names = Vec::new();
        for query in &self.queries {
            scan.tick(1)?;
            let Expr::Name(n) = query.node else {
                return Err("lexical query name unseen".into());
            };
            let owner = self.owner(scan, query.scope, n.id.as_str())?;
            let loc = self.module.location(n);
            let mut binding = self.binding_at(scan, owner, (loc.line, loc.column), n.id.as_str())?;
            remap(&mut binding,"owner",&references)?;
            let receiver = self.receiver(owner, n.id.as_str())?;
            scan.tick(receiver.map_or(0,str::len))?;
            let scope=references.get(&query.scope).ok_or("name scope reference unseen")?;
            scan.keep(&mut names,json!({"line":loc.line,"column":loc.column,"name":n.id.as_str(),
                "scope":scope,"binding":binding,"receiver":receiver}))?;
        }
        scan.tick(names.len().saturating_add(scopes.len()))?;
        names.sort_by_key(|n| {
            (
                n.get("line").and_then(Value::as_i64),
                n.get("column").and_then(Value::as_i64),
            )
        });
        let mut by_node=Vec::new();
        let root=references.get(&0).ok_or("root scope reference unseen")?;
        scan.keep(&mut by_node,json!([["Module",1,1,0],root]))?;
        for (node, scope) in &self.nodes {
            scan.tick(1)?;
            let scope=references.get(scope).ok_or("node scope reference unseen")?;
            scan.keep(&mut by_node,json!([node,scope]))?;
        }
        by_node.sort_by(|a, b| node_key(a).cmp(&node_key(b)));
        let queries = self.extra_queries(scan, input,&references)?;
        Ok(
            json!({"scopes":scopes,"names":names,"by_node":by_node,"queries":queries,"generic_header_numeric_lines":self.numeric}),
        )
    }

    fn extra_queries(&self, scan: &mut Scan, input: &Value, references: &HashMap<usize,usize>) -> Result<Vec<Value>> {
        let mut rows = Vec::new();
        let Some(queries) = input.get("queries") else {
            return Ok(rows);
        };
        for query in queries.as_array().ok_or("invalid lexical queries")? {
            scan.tick(1)?;
            let kind = text(query, "kind")?;
            let line = query
                .get("line")
                .and_then(Value::as_i64)
                .ok_or("query line unseen")?;
            let column = query
                .get("column")
                .and_then(Value::as_i64)
                .ok_or("query column unseen")?;
            let name = text(query, "name")?;
            let scope = *self
                .by_site
                .get(&(kind, line, column))
                .ok_or("lexical query site unseen")?;
            let owner = self.owner(scan, scope, name)?;
            let mut binding = self.binding_at(scan, owner, (line, column), name)?;
            remap(&mut binding,"owner",references)?;
            let receiver=self.receiver(owner,name)?;
            scan.tick(receiver.map_or(0,str::len))?;
            scan.keep(
                &mut rows,
                json!({"kind":kind,"line":line,"column":column,"name":name,
                "binding":binding,"receiver":receiver}),
            )?;
        }
        Ok(rows)
    }
}

fn scope_key(n: &Value) -> (Option<&str>, Option<i64>, Option<i64>) {
    (
        n.get("qualified_name").and_then(Value::as_str),
        n.get("node").and_then(|v| v.get(1)).and_then(Value::as_i64),
        n.get("node").and_then(|v| v.get(3)).and_then(Value::as_i64),
    )
}

fn node_key(n: &Value) -> (Option<&str>, Option<i64>, Option<i64>, Option<i64>) {
    let node = n.get(0);
    (
        node.and_then(|n| n.get(0)).and_then(Value::as_str),
        node.and_then(|n| n.get(1)).and_then(Value::as_i64),
        node.and_then(|n| n.get(2)).and_then(Value::as_i64),
        node.and_then(|n| n.get(3)).and_then(Value::as_i64),
    )
}

fn remap(value: &mut Value, key: &str, references: &HashMap<usize,usize>) -> Result<()> {
    let value=value.get_mut(key).ok_or("scope reference field unseen")?;
    if value.is_null() {return Ok(());}
    let id=value.as_u64().and_then(|n|usize::try_from(n).ok()).ok_or("invalid scope reference")?;
    *value=json!(references.get(&id).ok_or("scope reference unseen")?);
    Ok(())
}
