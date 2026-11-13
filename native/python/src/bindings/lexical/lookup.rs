// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Name ownership, binding records and the lossless lexical dump projection.

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
        // A child's free variable appears in each intervening compiler table.
        for id in (1..self.scopes.len()).rev() {
            scan.tick(1)?;
            scan.tick(self.scope(id)?.seen.len())?;
            let names: Vec<_> = self.scope(id)?.seen.iter().cloned().collect();
            for name in names {
                scan.tick(1)?;
                if self.scope(id)?.locals.contains(&name) || self.scope(id)?.globals.contains(&name)
                {
                    continue;
                }
                let mut parent = self.scope(id)?.parent;
                let mut crossed = Vec::new();
                while let Some(p) = parent {
                    scan.tick(1)?;
                    let scope = self.scope(p)?;
                    if scope.globals.contains(&name) {
                        break;
                    }
                    if scope.kind != Kind::Class && scope.locals.contains(&name) {
                        for p in crossed {
                            scan.tick(1)?;
                            self.scope_mut(p)?.seen.insert(name.clone());
                        }
                        break;
                    }
                    crossed.push(p);
                    parent = scope.parent;
                }
            }
        }
        let sites = std::mem::take(&mut self.sites);
        for (scope, name, site) in sites {
            scan.tick(1)?;
            if let Some(owner) = self.owner(scan, scope, &name)? {
                self.scope_mut(owner)?
                    .bindings
                    .entry(name)
                    .or_default()
                    .push(site);
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
            if scope.locals.contains(name) {
                return Ok(Some(id));
            }
            let mut parent = scope.parent;
            while let Some(p) = parent {
                scan.tick(1)?;
                let scope = self.scope(p)?;
                if scope.inlined {
                    if scope.locals.contains(name) {
                        return Ok(Some(p));
                    }
                } else if scope.kind != Kind::Class {
                    return self.owner(scan, p, name);
                }
                parent = scope.parent;
            }
            return Ok(None);
        }
        if !scope.table {
            return Ok(None);
        }
        // symtable stores the mangled spelling; lookup of the source spelling raises KeyError.
        if scope.private_context && name.starts_with("__") && !name.ends_with("__") {
            return Ok(Some(0));
        }
        if id == 0 || scope.locals.contains(name) {
            return Ok(Some(id));
        }
        if scope.globals.contains(name) || !scope.seen.contains(name) {
            return Ok(Some(0));
        }
        let mut parent = scope.parent;
        while let Some(p) = parent {
            scan.tick(1)?;
            let scope = self.scope(p)?;
            if scope.inlined {
                if scope.locals.contains(name) {
                    return Ok(Some(p));
                }
            } else {
                if !scope.table {
                    return Ok(None);
                }
                if scope.kind == Kind::Parameters || scope.kind == Kind::Alias {
                    return Ok(None);
                }
                if scope.globals.contains(name) {
                    return Ok(Some(0));
                }
                if scope.kind == Kind::Function || scope.kind == Kind::Comprehension {
                    if scope.locals.contains(name) {
                        return Ok(Some(p));
                    }
                }
            }
            parent = scope.parent;
        }
        Ok(Some(0))
    }

    fn binding(
        &self,
        scan: &mut Scan,
        owner: Option<usize>,
        node: &Expr,
        name: &str,
    ) -> Result<Value> {
        let Some(id) = owner else {
            return Ok(
                json!({"owner": null, "targets": [], "kind": "unknown", "uncertain": false}),
            );
        };
        let scope = self.scope(id)?;
        let sites = scope.bindings.get(name).map_or(&[][..], Vec::as_slice);
        if scope.kind == Kind::Class && !sites.is_empty() {
            let at = self.module.location(node);
            let mut after = true;
            for site in sites {
                scan.tick(1)?;
                let (_, line, _, column) = self.site(&site.node);
                after &= (line, column) > (at.line, at.column);
            }
            if after {
                return self.binding(scan, Some(0), node, name);
            }
        }
        let mut targets = BTreeSet::new();
        let mut kinds = BTreeSet::new();
        let mut conditional = false;
        for site in sites {
            scan.tick(1)?;
            conditional |= site.conditional;
            let declaration = match &site.node {
                Node::Stmt(Stmt::FunctionDef(n)) => Some(n.name.as_str()),
                Node::Stmt(Stmt::ClassDef(n)) => Some(n.name.as_str()),
                _ => None,
            };
            if let Some(name) = declaration {
                targets.insert(scan.owner(&scope.qualified, name)?.to_string());
                kinds.insert("declaration".to_owned());
            } else if matches!(site.node, Node::Stmt(Stmt::Import(_) | Stmt::ImportFrom(_))) {
                let (_, line, _, column) = self.site(&site.node);
                if let Some((target, kind)) = self.aliases.get(&(line, column, name.to_owned())) {
                    scan.tick(target.len())?;
                    targets.insert(target.clone());
                    kinds.insert(kind.clone());
                }
            }
        }
        let kind = if !targets.is_empty() {
            if kinds.len() == 1 {
                kinds.first().map_or("mixed", String::as_str)
            } else {
                "mixed"
            }
        } else if !sites.is_empty() || id != 0 {
            "local"
        } else if scope.bindings.contains_key("*") {
            "unknown"
        } else {
            "unbound"
        };
        let uncertain = if !targets.is_empty() {
            sites.len() != 1 || targets.len() != 1 || conditional
        } else if !sites.is_empty() || id != 0 {
            sites.len() != 1 || conditional
        } else {
            false
        };
        scan.tick(scope.qualified.len().saturating_add(targets.len()))?;
        Ok(
            json!({"owner": scope.qualified.as_ref(), "targets": targets, "kind": kind, "uncertain": uncertain}),
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

    fn site(&self, node: &Node<'_>) -> (&'static str, i64, i64, i64) {
        let range = match node {
            Node::Stmt(Stmt::FunctionDef(n)) => Some(Def::Function(n).range(self.module.text())),
            Node::Stmt(Stmt::ClassDef(n)) => Some(Def::Class(n).range(self.module.text())),
            Node::Stmt(n) => Some(n.range()),
            Node::Expr(n) => Some(self.expression_range(n)),
            Node::Arg(n) => Some(TextRange::new(n.name.start(), n.end())),
            Node::Handler(n) => Some(n.range()),
            Node::Pattern(n) => Some(n.range()),
            _ => None,
        };
        let loc = range.map(|r| self.module.location(&r));
        (
            node.kind(),
            loc.as_ref().map_or(1, |l| l.line),
            loc.as_ref().map_or(1, |l| l.end_line),
            loc.map_or(0, |l| l.column),
        )
    }

    pub(super) fn dump(&self, scan: &mut Scan) -> Result<Value> {
        let mut scopes = Vec::new();
        for (id, scope) in self.scopes.iter().enumerate() {
            scan.tick(1)?;
            if id != 0 && !self.touched.contains(&id) {
                continue;
            }
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
            let parent = scope
                .parent
                .map(|p| self.scope(p).map(|s| s.qualified.as_ref()))
                .transpose()?;
            let row = json!({"qualified_name": scope.qualified.as_ref(), "definition_id": scope.identity,
                "parent": parent, "table": scope.table, "inlined": scope.inlined,
                "local_names": if scope.inlined { scope.locals.iter().collect::<Vec<_>>() } else { Vec::new() },
                "blocked_names": scope.blocked, "bindings": bindings,
                "node": scope.node.as_ref().map(|n| self.site(n)).unwrap_or(("Module", 1, 1, 0)),
            });
            scan.keep(&mut scopes, row)?;
        }
        let mut names = Vec::new();
        for query in &self.queries {
            scan.tick(1)?;
            let Expr::Name(n) = query.node else {
                return Err("lexical query name unseen".into());
            };
            let owner = self.owner(scan, query.scope, n.id.as_str())?;
            let binding = self.binding(scan, owner, query.node, n.id.as_str())?;
            let receiver = self.receiver(owner, n.id.as_str())?;
            let loc = self.module.location(n);
            let row = json!({"line": loc.line, "column": loc.column, "name": n.id.as_str(),
                "scope": self.scope(query.scope)?.qualified.as_ref(), "binding": binding, "receiver": receiver});
            scan.keep(&mut names, row)?;
        }
        scan.tick(names.len().saturating_add(scopes.len()))?;
        names.sort_by_key(|n| {
            (
                n.get("line").and_then(Value::as_i64),
                n.get("column").and_then(Value::as_i64),
            )
        });
        fn key(n: &Value) -> (Option<&str>, Option<i64>, Option<i64>) {
            (
                n.get("qualified_name").and_then(Value::as_str),
                n.get("node").and_then(|v| v.get(1)).and_then(Value::as_i64),
                n.get("node").and_then(|v| v.get(3)).and_then(Value::as_i64),
            )
        }
        scopes.sort_by(|a, b| key(a).cmp(&key(b)));
        Ok(json!({"scopes": scopes, "names": names, "generic_header_numeric_lines": self.numeric}))
    }
}
