// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol declarations of a module (AD-514): one record for each class, function, method and
//! class attribute that the module binds exactly once, in a form whose kind Python decides when
//! the statement runs.
//!
//! The reader writes nothing that it cannot prove. A name that another statement binds, a
//! decorator that may replace the object, a base that may change the kind and a text that native
//! cannot write give no record: the model then reads the name as absent, which decides nothing
//! (AD-512). The sites (bases, calls, references) are not written here.

use std::collections::HashMap;

use archkeel_facts::data::{CallableData, ClassData, Declared};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nested::{MemberInventory, Parameter, VisibilityDetail};
use archkeel_facts::vocab::{Area, ClassKind, EvidenceClass, InventoryStatus, MemberKind};
use archkeel_facts::{Record, SymbolFact};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::Ranged;
use serde_json::{Map, Value};

use super::binders::Binders;
use super::bound::Bound;
use super::writes;
use crate::declare::{definition_id, signature, visibility};
use crate::module::definition::Def;
use crate::module::{EvidenceMap, Module};
use kind::{Kind, Reading};
use reader::{Reader, Unwritable};

mod kind;
mod members;
mod reader;

/// Why a member list is never complete: a base, a metaclass, a decorator and a write after the
/// class body can add a member that the body does not show.
const PARTIAL: &str =
    "a base, a metaclass, a decorator or a write after the class body can add a member";

/// The declarations of one module. A module that native cannot read completely has none.
pub(crate) fn records(
    module: &Module,
    binders: &Binders,
    evidence: &mut EvidenceMap,
) -> Vec<Record<SymbolFact>> {
    let mut scratch = EvidenceMap::new();
    let mut writer = Writer {
        scan: Reader {
            module,
            evidence_map: &mut scratch,
        },
        binders,
        // An attribute write whose base is not `self` can add or replace a member of any class.
        open: writes::bases(&module.tree.body)
            .iter()
            .any(|base| !matches!(base, Expr::Name(name) if name.id.as_str() == "self")),
        out: Vec::new(),
    };
    let done = writer.run();
    let mut out = writer.out;
    if done.is_err() {
        return Vec::new();
    }
    evidence.extend(scratch);
    out.sort_by(|left, right| left.id.as_str().cmp(right.id.as_str()));
    out
}

/// Remember a class of the module body with a record, and its body for the nested classes.
fn keep<'a>(
    found: Option<(Frame<'a>, Kind)>,
    name: &str,
    local: &mut HashMap<String, Kind>,
    pending: &mut Vec<Frame<'a>>,
) {
    if let Some((frame, kind)) = found {
        local.insert(name.to_owned(), kind);
        pending.push(frame);
    }
}

/// The classes of a class body that bind their name once.
fn nested<'a>(frame: &Frame<'a>) -> Vec<&'a StmtClassDef> {
    let found = frame
        .node
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(node)
                if frame
                    .bound
                    .sole(node.name.as_str(), statement.range().start()) =>
            {
                Some(node)
            }
            _ => None,
        });
    found.collect()
}

/// A class with a record whose body is not read yet.
struct Frame<'a> {
    node: &'a StmtClassDef,
    qualname: String,
    id: String,
    bound: Bound,
}

struct Writer<'m, 'b> {
    scan: Reader<'m>,
    binders: &'b Binders,
    open: bool,
    out: Vec<Record<SymbolFact>>,
}

impl<'m> Writer<'m, '_> {
    fn run(&mut self) -> Result<(), Unwritable> {
        let module: &'m Module = self.scan.module;
        let body = &module.tree.body;
        let bound = Bound::of(body);
        let mut pending = Vec::new();
        // The classes of the module body with a record, by name.
        let mut local: HashMap<String, Kind> = HashMap::new();
        for statement in body {
            let start = statement.range().start();
            match statement {
                Stmt::FunctionDef(node) if bound.sole(node.name.as_str(), start) => {
                    self.function(node)?;
                }
                Stmt::ClassDef(node) if bound.sole(node.name.as_str(), start) => {
                    let reading = Reading::top(body, &bound, self.binders, &local);
                    let found = self.class(node, &reading, None)?;
                    keep(found, node.name.as_str(), &mut local, &mut pending);
                }
                _ => {}
            }
        }
        while let Some(frame) = pending.pop() {
            let reading = Reading::top(body, &bound, self.binders, &local).within(&frame.bound);
            for node in nested(&frame) {
                let found = self.class(node, &reading, Some(&frame))?;
                pending.extend(found.map(|(next, _)| next));
            }
        }
        Ok(())
    }

    /// A function of the module body that no decorator can replace.
    fn function(&mut self, node: &StmtFunctionDef) -> Result<(), Unwritable> {
        if !node.decorator_list.is_empty() {
            return Ok(());
        }
        let holder = &self.scan.module.name;
        let header = self.header(node.name.as_str(), holder, None);
        let fact = self.callable(node, header, None)?;
        self.push(Def::Function(node), (holder, node.name.as_str()), fact)
    }

    /// The header of a declaration: where it is and how its name reads.
    fn header(&self, name: &str, holder: &str, parent: Option<(&str, &str)>) -> Declared {
        let module = self.scan.module;
        Declared {
            module: ModuleName::new(&module.name),
            package: PackageName::new(&module.package),
            name: name.to_owned(),
            qualified_name: format!("{holder}.{name}"),
            parent: parent.map(|(qualname, _)| qualname.to_owned()),
            lexical_parent_id: parent.map(|(_, id)| FactId::new(id)),
            unique: true,
            visibility: serde_json::from_value::<VisibilityDetail>(visibility(name)).unwrap_or(
                VisibilityDetail {
                    basis: "convention".to_owned(),
                    kind: "public".to_owned(),
                    spelling: name.to_owned(),
                },
            ),
        }
    }

    /// A function or a method with the text of its signature.
    fn callable(
        &mut self,
        node: &StmtFunctionDef,
        header: Declared,
        method: Option<archkeel_facts::vocab::MethodKind>,
    ) -> Result<SymbolFact, Unwritable> {
        let mut map = Map::new();
        signature(&|expr| self.scan.text(expr), node, &mut map)?;
        let mut data = CallableData::declared(header, method);
        data.parameters = serde_json::from_value::<Vec<Parameter>>(
            map.remove("parameters").unwrap_or(Value::Null),
        )
        .map_err(|_| Unwritable)?;
        data.returns = match map.remove("returns") {
            Some(Value::String(text)) => Some(text),
            _ => None,
        };
        data.is_async = node.is_async.then_some(true);
        data.signature_complete = Some(true);
        if let Some(decorator) = node.decorator_list.first() {
            if let Expr::Name(name) = &decorator.expression {
                data.decorators = vec![name.id.to_string()];
            }
        }
        Ok(match method {
            Some(_) => SymbolFact::Method(data),
            None => SymbolFact::Function(data),
        })
    }

    /// The record of a class and of its methods; the frame of the class when its body holds
    /// classes to read. A class with no proven kind has no record and no member.
    fn class<'a>(
        &mut self,
        node: &'a StmtClassDef,
        reading: &Reading<'_>,
        owner: Option<&Frame<'_>>,
    ) -> Result<Option<(Frame<'a>, Kind)>, Unwritable> {
        if !node.decorator_list.is_empty() {
            return Ok(None);
        }
        let Some(class_kind) = kind::of(node, reading) else {
            return Ok(None);
        };
        let module: &'m Module = self.scan.module;
        let name = node.name.as_str();
        let holder = owner.map_or(module.name.as_str(), |frame| frame.qualname.as_str());
        let qualname = format!("{holder}.{name}");
        let id = definition_id(module, Def::Class(node), &qualname);
        let bound = Bound::of(&node.body);
        let (attributes, methods) = if self.open {
            (members::open(), Vec::new())
        } else {
            let attributes = members::attributes(&mut self.scan, node, &bound, class_kind)?;
            (attributes, self.methods(node, &bound, &qualname, &id)?)
        };
        let parent = owner.map(|frame| (frame.qualname.as_str(), frame.id.as_str()));
        let header = self.header(name, holder, parent);
        let word = match class_kind {
            Kind::Plain => ClassKind::Class,
            Kind::Protocol => ClassKind::Protocol,
            Kind::Enum => ClassKind::Enum,
        };
        let mut data = ClassData::declared(header, word);
        data.enum_members = attributes.literals;
        data.member_inventories = vec![
            inventory(
                MemberKind::Attribute,
                attributes
                    .declarations
                    .iter()
                    .map(|item| item.definition_id.clone())
                    .collect(),
            ),
            inventory(
                MemberKind::Method,
                methods
                    .iter()
                    .map(|(_, id)| FactId::new(id.as_str()))
                    .collect(),
            ),
        ];
        data.attribute_declarations = attributes.declarations;
        self.push(Def::Class(node), (holder, name), SymbolFact::Class(data))?;
        for (record, _) in methods {
            self.out.push(record);
        }
        let frame = Frame {
            node,
            qualname,
            id,
            bound,
        };
        Ok(Some((frame, class_kind)))
    }

    /// The methods of a class body that bind their name once, each with its record and id.
    fn methods(
        &mut self,
        node: &StmtClassDef,
        bound: &Bound,
        qualname: &str,
        id: &str,
    ) -> Result<Vec<(Record<SymbolFact>, String)>, Unwritable> {
        let module: &'m Module = self.scan.module;
        let mut found = Vec::new();
        for statement in &node.body {
            let Stmt::FunctionDef(function) = statement else {
                continue;
            };
            let name = function.name.as_str();
            if !bound.sole(name, statement.range().start()) {
                continue;
            }
            let Some(method) = members::method_kind(function, self.binders) else {
                continue;
            };
            let header = self.header(name, qualname, Some((qualname, id)));
            let fact = self.callable(function, header, Some(method))?;
            let record = self.record(Def::Function(function), name, qualname, fact)?;
            let own = definition_id(
                module,
                Def::Function(function),
                &format!("{qualname}.{name}"),
            );
            found.push((record, own));
        }
        Ok(found)
    }

    fn push(
        &mut self,
        def: Def<'_>,
        (holder, name): (&str, &str),
        fact: SymbolFact,
    ) -> Result<(), Unwritable> {
        let record = self.record(def, name, holder, fact)?;
        self.out.push(record);
        Ok(())
    }

    fn record(
        &mut self,
        def: Def<'_>,
        name: &str,
        holder: &str,
        fact: SymbolFact,
    ) -> Result<Record<SymbolFact>, Unwritable> {
        let module = self.scan.module;
        let qualname = format!("{holder}.{name}");
        let range = def.range(module.text());
        let evidence = self.scan.evidence(&range);
        let mut subjects = vec![qualname.clone(), module.name.clone()];
        subjects.sort();
        Ok(Record {
            id: FactId::new(definition_id(module, def, &qualname)),
            evidence_class: EvidenceClass::Fact,
            area: Area::RepositoryTopology,
            title: name.to_owned(),
            subjects,
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data: fact,
        })
    }
}

fn inventory(kind: MemberKind, definition_ids: Vec<FactId>) -> MemberInventory {
    MemberInventory {
        definition_ids,
        kind,
        reason: Some(PARTIAL.to_owned()),
        schema_version: "1.0.0".to_owned(),
        status: InventoryStatus::Partial,
    }
}

#[cfg(test)]
#[path = "declared_tests.rs"]
mod tests;
