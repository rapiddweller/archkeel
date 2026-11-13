// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typing signals from source and explicit record inputs, not resolved guesses.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::SignalData;
use archkeel_facts::envelope::Evidence;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass, Signal};
use archkeel_facts::{Record, SignalFact};
use ruff_python_ast::{Expr, Parameter, Stmt};
use ruff_text_size::{Ranged, TextRange};
use serde_json::{json, Value};

use super::scan::{Result, Scan};
use crate::module::{definition::Def, EvidenceMap, Module};
use crate::pyast::Node;

mod inputs;
mod statements;

pub(super) fn collect(module: &Module, scan: &mut Scan, input: &Value) -> Result<Value> {
    let mut evidence = EvidenceMap::new();
    for item in inputs::array(input, "evidence")? {
        scan.tick(1)?;
        scan.output.value(item)?;
        let item: Evidence = serde_json::from_value(item.clone()).map_err(|e| e.to_string())?;
        evidence.insert(item.id.as_str().to_owned(), item);
    }
    let mut collector = Collector {
        module,
        evidence,
        records: Vec::new(),
        statements: BTreeMap::new(),
    };
    for stmt in &module.tree.body {
        scan.tick(1)?;
        collector.child(scan, Node::Stmt(stmt), &module.name, 0)?;
    }
    collector.comments(scan)?;
    collector.dynamic(scan, input)?;
    collector.boundaries(scan, input)?;
    scan.tick(
        collector
            .records
            .len()
            .saturating_add(collector.evidence.len()),
    )?;
    collector
        .records
        .sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
    Ok(
        json!({"typing_signals": collector.records, "evidence": collector.evidence.into_values().collect::<Vec<_>>()}),
    )
}

struct Collector<'a> {
    module: &'a Module,
    evidence: EvidenceMap,
    records: Vec<Record<SignalFact>>,
    statements: BTreeMap<i64, (String, &'a Stmt)>,
}

fn data(owner: &str, signal: Signal) -> SignalData {
    SignalData {
        owner: owner.into(),
        signal,
        annotation: None,
        expression: None,
        line: None,
        positions: None,
        qualified_name: None,
        statement: None,
        tag: None,
    }
}

fn fact(data: SignalData) -> SignalFact {
    match data.signal {
        Signal::AnyAnnotation => SignalFact::AnyAnnotation(data),
        Signal::DictAnyAnnotation => SignalFact::DictAnyAnnotation(data),
        Signal::CallableAnyAnnotation => SignalFact::CallableAnyAnnotation(data),
        Signal::ObjectAnnotation => SignalFact::ObjectAnnotation(data),
        Signal::CastCall => SignalFact::CastCall(data),
        Signal::GetattrCall => SignalFact::GetattrCall(data),
        Signal::HasattrCall => SignalFact::HasattrCall(data),
        Signal::EvalCall => SignalFact::EvalCall(data),
        Signal::ExecCall => SignalFact::ExecCall(data),
        Signal::DynamicImport => SignalFact::DynamicImport(data),
        Signal::TypeIgnore => SignalFact::TypeIgnore(data),
        Signal::MissingCrossPackageAnnotation => SignalFact::MissingCrossPackageAnnotation(data),
    }
}

impl<'a> Collector<'a> {
    fn keep(&mut self, scan: &mut Scan, record: Record<SignalFact>) -> Result<()> {
        let row = serde_json::to_value(&record).map_err(|e| e.to_string())?;
        scan.output.value(&row)?;
        self.records.push(record);
        Ok(())
    }

    fn annotation(
        &mut self,
        scan: &mut Scan,
        range: TextRange,
        annotation: Option<&Expr>,
        owner: &str,
    ) -> Result<()> {
        let Some(annotation) = annotation else {
            return Ok(());
        };
        let Some(text) = super::class::text(scan, annotation, self.module.text())? else {
            return Ok(());
        };
        if text.is_empty() {
            return Ok(());
        }
        let mut names = BTreeSet::new();
        for node in scan.walk(Node::Expr(annotation))? {
            scan.tick(1)?;
            match node {
                Node::Expr(Expr::Name(n)) => {
                    names.insert(n.id.as_str());
                }
                Node::Expr(Expr::Attribute(n)) => {
                    names.insert(n.attr.as_str());
                }
                _ => {}
            }
        }
        let root = if let Expr::Subscript(n) = annotation {
            super::class::text(scan, &n.value, self.module.text())?
                .unwrap_or_default()
                .rsplit('.')
                .next()
                .unwrap_or("")
                .to_owned()
        } else {
            String::new()
        };
        let mut kinds = Vec::new();
        if names.contains("Any") {
            kinds.push(Signal::AnyAnnotation);
        }
        if names.contains("Any") && matches!(root.as_str(), "dict" | "Dict") {
            kinds.push(Signal::DictAnyAnnotation);
        }
        if names.contains("Any") && root == "Callable" {
            kinds.push(Signal::CallableAnyAnnotation);
        }
        if matches!(annotation, Expr::Name(n) if n.id.as_str() == "object") {
            kinds.push(Signal::ObjectAnnotation);
        }
        kinds.sort_by_key(|k| k.as_str());
        for signal in kinds {
            scan.tick(1)?;
            let evidence_id = self.module.evidence(&mut self.evidence, &range);
            let line = self.module.location(&range).line;
            let id = stable_id(
                "TYPE",
                &[
                    Part::Text(&self.module.rel),
                    Part::Number(line),
                    Part::Text(owner),
                    Part::Text(signal.as_str()),
                    Part::Text(&text),
                ],
            );
            scan.tick(owner.len().saturating_add(text.len()))?;
            let mut data = data(owner, signal);
            data.annotation = Some(text.clone());
            self.keep(
                scan,
                Record {
                    id: FactId::new(id),
                    evidence_class: EvidenceClass::Fact,
                    area: Area::TypeArchitecture,
                    title: format!("{owner}: {text}"),
                    subjects: vec![owner.into()],
                    evidence_ids: vec![EvidenceId::new(evidence_id)],
                    fact_ids: Vec::new(),
                    data: fact(data),
                },
            )?;
        }
        Ok(())
    }

    fn parameter(&mut self, scan: &mut Scan, p: &Parameter, owner: &str) -> Result<()> {
        scan.tick(owner.len().saturating_add(p.name.len()))?;
        let owner = format!("{owner}:{}", p.name);
        self.annotation(
            scan,
            TextRange::new(p.name.start(), p.end()),
            p.annotation.as_deref(),
            &owner,
        )
    }

    fn child(&mut self, scan: &mut Scan, node: Node<'a>, scope: &str, depth: usize) -> Result<()> {
        scan.tick(1)?;
        if depth > 100 {
            return Err("typing signal depth limit exceeded (100 levels)".into());
        }
        self.statement_lines(scan, &node, scope)?;
        let mut owner = None;
        match &node {
            Node::Stmt(Stmt::AnnAssign(n)) => {
                let text = super::class::text(scan, &n.target, self.module.text())?;
                let owner = text
                    .filter(|t| !t.is_empty())
                    .map(|t| format!("{scope}.{t}"));
                self.annotation(
                    scan,
                    n.range,
                    Some(&n.annotation),
                    owner.as_deref().unwrap_or(scope),
                )?;
            }
            Node::Stmt(Stmt::FunctionDef(n)) => {
                let name = scan.owner(scope, n.name.as_str())?;
                for p in n
                    .parameters
                    .posonlyargs
                    .iter()
                    .chain(&n.parameters.args)
                    .chain(&n.parameters.kwonlyargs)
                {
                    scan.tick(1)?;
                    self.parameter(scan, &p.parameter, &name)?;
                }
                scan.tick(name.len())?;
                self.annotation(
                    scan,
                    Def::Function(n).range(self.module.text()),
                    n.returns.as_deref(),
                    &format!("{name}:return"),
                )?;
                owner = Some(name);
            }
            Node::Stmt(Stmt::ClassDef(n)) => {
                owner = Some(scan.owner(scope, n.name.as_str())?);
            }
            _ => {}
        }
        let scope = owner.as_deref().unwrap_or(scope);
        for child in scan.children(&node)? {
            scan.tick(1)?;
            self.child(scan, child, scope, depth + 1)?;
        }
        Ok(())
    }

    fn comments(&mut self, scan: &mut Scan) -> Result<()> {
        let tokens = crate::parse::fact_tokens::tokens(self.module.text(), &mut scan.work)?;
        for range in tokens.comments {
            scan.tick(1)?;
            let comment = self
                .module
                .text()
                .get(range.start().to_usize()..range.end().to_usize())
                .ok_or("comment span unseen")?;
            scan.tick(comment.len())?;
            let Some((_, tag)) = comment.split_once("type: ignore") else {
                continue;
            };
            let loc = self.module.location(&range);
            let source = self
                .module
                .excerpt(loc.line, loc.line)
                .ok_or("comment line unseen")?;
            scan.tick(source.len())?;
            let prefix = source
                .get(..usize::try_from(loc.column).map_err(|_| "comment column unseen")?)
                .ok_or("comment prefix unseen")?;
            let column =
                i64::try_from(prefix.chars().count()).map_err(|_| "comment column unseen")?;
            let context = self.statements.get(&loc.line);
            let attached = if let Some((_, stmt)) = context {
                let start = self.module.location(*stmt);
                let line = self
                    .module
                    .excerpt(start.line, start.line)
                    .ok_or("statement line unseen")?;
                scan.tick(line.len())?;
                let prefix = line
                    .get(..usize::try_from(start.column).map_err(|_| "statement column unseen")?)
                    .ok_or("statement prefix unseen")?;
                !source
                    .get(..usize::try_from(loc.column).map_err(|_| "comment column unseen")?)
                    .unwrap_or("")
                    .trim()
                    .is_empty()
                    && prefix.trim().is_empty()
            } else {
                false
            };
            let statement = if attached {
                let (_, stmt) = context.ok_or("attached statement unseen")?;
                statements::text(scan, self.module, stmt)?
            } else {
                String::new()
            };
            let qualified = context.map_or(self.module.name.as_str(), |(name, _)| name);
            let evidence = Evidence::at(
                &self.module.rel,
                loc.line,
                loc.end_line,
                column,
                crate::module::rstrip(&source),
            );
            let evidence_id = evidence.id.clone();
            self.evidence.insert(evidence.id.as_str().into(), evidence);
            let mut data = data(&self.module.name, Signal::TypeIgnore);
            data.qualified_name = Some(qualified.into());
            data.line = Some(loc.line);
            data.statement = Some(statement);
            data.tag = Some(tag.trim().into());
            let id = stable_id(
                "TYPE",
                &[
                    Part::Text(&self.module.rel),
                    Part::Number(loc.line),
                    Part::Text("type-ignore"),
                ],
            );
            self.keep(
                scan,
                Record {
                    id: FactId::new(id),
                    evidence_class: EvidenceClass::Fact,
                    area: Area::TypeArchitecture,
                    title: format!("{}:{} uses type: ignore", self.module.rel, loc.line),
                    subjects: vec![self.module.name.clone()],
                    evidence_ids: vec![evidence_id],
                    fact_ids: Vec::new(),
                    data: fact(data),
                },
            )?;
        }
        Ok(())
    }

    fn statement_lines(&mut self, scan: &mut Scan, node: &Node<'a>, scope: &str) -> Result<()> {
        let Node::Stmt(stmt) = node else {
            return Ok(());
        };
        if matches!(stmt, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            return Ok(());
        }
        let loc = self.module.location(*stmt);
        for line in loc.line..=loc.end_line {
            scan.tick(1usize.saturating_add(scope.len()))?;
            self.statements.insert(line, (scope.into(), stmt));
        }
        Ok(())
    }
}
