// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol declarations of a module (AD-518): one record for each class, function, method and
//! class attribute that the module binds exactly once, in a form whose kind Python decides when
//! the statement runs.
//!
//! The reader writes nothing that it cannot prove. A name that another statement binds, a
//! decorator that may replace the object, a base that may change the kind and a text that native
//! cannot write give no record: the model then reads the name as absent, which decides nothing
//! (AD-512). The sites (bases, calls, references) are not written here.

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::{CallableData, ClassData, Declared};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::nested::{BaseDeclaration, MemberInventory, Parameter};
use archkeel_facts::vocab::{
    Area, ClassKind, EvidenceClass, InventoryStatus, MemberKind, MethodKind, RelationshipKind,
    Status,
};
use archkeel_facts::{Record, SymbolFact};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::Ranged;
use serde_json::{Map, Value};

use super::binders::Binders;
use super::bound::Bound;
use crate::declare::{definition_id, signature};
use crate::module::definition::Def;
use crate::module::{EvidenceMap, Module};
use kind::{BaseSite, Kind, Local, Reading};
use reader::{header, Reader, Unwritable};

mod escapes;
mod found;
mod kind;
mod members;
mod reader;
mod scope;
mod shape_names;
mod shape_text;
mod shapes;
mod sites;
mod values;

pub(crate) use found::{Found, Source};
pub(crate) use shapes::attach as attach_shapes;
pub(crate) use sites::{site_records, Context};

pub(in crate::survey) use escapes::{all as scan_escapes, Escapes};

/// Why a member list is never complete: a base, a metaclass, a decorator and a write after the
/// class body can add a member that the body does not show.
const PARTIAL: &str =
    "a base, a metaclass, a decorator or a write after the class body can add a member";

/// The declarations of one module. A module that native cannot read completely has none.
pub(crate) fn records<'m>(
    module: &'m Module,
    binders: &Binders,
    escapes: Escapes,
    evidence: &mut EvidenceMap,
) -> Found<'m> {
    let mut scratch = EvidenceMap::new();
    let mut writer = Writer {
        scan: Reader {
            module,
            evidence_map: &mut scratch,
            shadowed: Reader::shadowed(binders),
        },
        binders,
        open: escapes.open,
        escaped: escapes.escaped,
        out: Vec::new(),
        sources: Vec::new(),
        constructible: HashSet::new(),
    };
    let done = writer.run();
    let Writer {
        mut out,
        sources,
        constructible,
        ..
    } = writer;
    if done.is_err() {
        return Found::default();
    }
    evidence.extend(scratch);
    out.sort_by(|left, right| left.id.as_str().cmp(right.id.as_str()));
    Found {
        index: 0,
        records: out,
        sources,
        constructible,
    }
}

/// Remember a class of the module body with a record, and its body for the nested classes.
fn keep<'a>(
    found: Option<(Frame<'a>, Local)>,
    name: &str,
    local: &mut HashMap<String, Local>,
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
    /// The members of the class are withheld, and so are its nested classes.
    open: bool,
}

struct Writer<'m, 'b> {
    scan: Reader<'m, 'b>,
    binders: &'b Binders,
    open: bool,
    escaped: HashSet<String>,
    out: Vec<Record<SymbolFact>>,
    sources: Vec<Source<'m>>,
    constructible: HashSet<String>,
}

impl<'m> Writer<'m, '_> {
    fn run(&mut self) -> Result<(), Unwritable> {
        let module: &'m Module = self.scan.module;
        let body = &module.tree.body;
        let bound = Bound::of(body);
        let mut pending = Vec::new();
        // The classes of the module body with a record, by name.
        let mut local: HashMap<String, Local> = HashMap::new();
        for statement in body {
            let start = statement.range().start();
            match statement {
                Stmt::FunctionDef(node) if bound.sole(node.name.as_str(), start) => {
                    self.function(node)?;
                }
                Stmt::ClassDef(node) if bound.sole(node.name.as_str(), start) => {
                    let reading = Reading::top((&module.name, body), &bound, self.binders, &local);
                    let found = self.class(node, &reading, None)?;
                    keep(found, node.name.as_str(), &mut local, &mut pending);
                }
                Stmt::Assign(_) | Stmt::AnnAssign(_) => {
                    let reading = Reading::top((&module.name, body), &bound, self.binders, &local);
                    let found = values::records(&mut self.scan, statement, &bound, &reading);
                    self.out.extend(found);
                }
                _ => {}
            }
        }
        while let Some(frame) = pending.pop() {
            let reading = Reading::top((&module.name, body), &bound, self.binders, &local)
                .within(&frame.bound);
            let inside = if frame.open {
                Vec::new()
            } else {
                nested(&frame)
            };
            for node in inside {
                let found = self.class(node, &reading, Some(&frame))?;
                pending.extend(found.map(|(next, _)| next));
            }
        }
        Ok(())
    }

    /// A function of the module body that no decorator can replace.
    fn function(&mut self, node: &'m StmtFunctionDef) -> Result<(), Unwritable> {
        if !node.decorator_list.is_empty() {
            return Ok(());
        }
        let holder = &self.scan.module.name;
        let header = self.header(node.name.as_str(), holder, None);
        let fact = self.callable(node, header, None)?;
        let qualname = format!("{holder}.{}", node.name.as_str());
        let id = definition_id(self.scan.module, Def::Function(node), &qualname);
        self.sources.push(Source {
            node,
            qualname,
            id,
            class_names: None,
        });
        self.push(Def::Function(node), (holder, node.name.as_str()), fact)
    }

    /// The header of a declaration: where it is and how its name reads.
    fn header(&self, name: &str, holder: &str, parent: Option<(&str, &str)>) -> Declared {
        header(self.scan.module, (name, holder), parent)
    }

    /// A function or a method with the text of its signature.
    fn callable(
        &mut self,
        node: &StmtFunctionDef,
        header: Declared,
        method: Option<archkeel_facts::vocab::MethodKind>,
    ) -> Result<SymbolFact, Unwritable> {
        let mut map = Map::new();
        // A text that native cannot write leaves the signature unread, not the module: the names
        // and kinds of the parameters stay, `signature_complete` is false (AD-550) and the written
        // types ride in the shapes.
        let complete = signature(&|expr| self.scan.text(expr), node, &mut map).is_ok();
        if !complete {
            map.clear();
            let lenient = |expr: Option<&Expr>| -> Result<Option<String>, Unwritable> {
                Ok(self.scan.text(expr).ok().flatten())
            };
            signature(&lenient, node, &mut map)?;
        }
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
        data.signature_complete = Some(complete);
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
    fn class(
        &mut self,
        node: &'m StmtClassDef,
        reading: &Reading<'_>,
        owner: Option<&Frame<'_>>,
    ) -> Result<Option<(Frame<'m>, Local)>, Unwritable> {
        if !node.decorator_list.is_empty() {
            return Ok(None);
        }
        let Some(found) = kind::of(node, reading) else {
            return Ok(None);
        };
        let class_kind = found.kind;
        let module: &'m Module = self.scan.module;
        let name = node.name.as_str();
        let holder = owner.map_or(module.name.as_str(), |frame| frame.qualname.as_str());
        let qualname = format!("{holder}.{name}");
        let id = definition_id(module, Def::Class(node), &qualname);
        let bound = Bound::of(&node.body);
        let open = self.open
            || owner.is_some_and(|frame| frame.open)
            || (owner.is_none() && self.escaped.contains(name));
        let (attributes, methods) = if open {
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
        // Each name that the class body binds, with a record or not: a method with a decorator
        // that this reader does not admit has no record, and `boundary_types` must not pass it
        // by (AD-550). A class whose members are withheld states none.
        data.class_members = (!open).then(|| {
            let mut names: Vec<String> = bound.names().into_iter().collect();
            names.sort();
            names
        });
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
        data.base_declarations = self.bases(&id, class_kind, &found.bases)?;
        // A class that a write or an escape can change may get a `__new__` outside its body.
        let constructible = class_kind == Kind::Plain
            && found.constructible
            && !open
            && !bound.names().contains("__new__");
        self.push(Def::Class(node), (holder, name), SymbolFact::Class(data))?;
        for (record, _) in methods {
            self.out.push(record);
        }
        let frame = Frame {
            node,
            qualname,
            id,
            bound,
            open,
        };
        if owner.is_none() && constructible {
            self.constructible.insert(frame.qualname.clone());
        }
        let local = Local {
            kind: class_kind,
            constructible,
        };
        Ok(Some((frame, local)))
    }

    /// `_base_declaration`: one resolved declaration for each base of a class. The list is the
    /// class statement, so a base that it does not name is a base that the class lacks.
    fn bases(
        &mut self,
        class: &str,
        class_kind: Kind,
        bases: &[BaseSite<'_>],
    ) -> Result<Vec<BaseDeclaration>, Unwritable> {
        let module = self.scan.module;
        let mut found = Vec::new();
        for base in bases {
            let expression = self.scan.text(Some(base.expr))?.unwrap_or_default();
            let crate::module::Location { line, column, .. } = module.location(base.expr);
            let relationship_kind = if base.protocol && class_kind != Kind::Protocol {
                RelationshipKind::Realizes
            } else {
                RelationshipKind::Inherits
            };
            let id = stable_id(
                "BASE",
                &[
                    Part::Text(class),
                    Part::Number(line),
                    Part::Number(column),
                    Part::Text(&expression),
                ],
            );
            found.push(BaseDeclaration {
                candidate_count: 1,
                candidates_truncated: None,
                evidence_ids: vec![EvidenceId::new(self.scan.evidence(base.expr))],
                expression,
                id: FactId::new(id),
                reason: Some("explicit base with a proven binding".to_owned()),
                relationship_kind,
                status: Status::Resolved,
                targets: vec![base.target.clone()],
            });
        }
        Ok(found)
    }

    /// The methods of a class body that bind their name once, each with its record and id.
    fn methods(
        &mut self,
        node: &'m StmtClassDef,
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
            if members::mangled(name) || !bound.sole(name, statement.range().start()) {
                continue;
            }
            let Some(method) = members::method_kind(function, self.binders) else {
                continue;
            };
            // The constructor is its own kind: its signature has no return position (AD-550).
            let method = match (name, method) {
                ("__init__", MethodKind::Instance) => MethodKind::Constructor,
                (_, kind) => kind,
            };
            let header = self.header(name, qualname, Some((qualname, id)));
            let fact = self.callable(function, header, Some(method))?;
            let record = self.record(Def::Function(function), name, qualname, fact)?;
            let own = definition_id(
                module,
                Def::Function(function),
                &format!("{qualname}.{name}"),
            );
            self.sources.push(Source {
                node: function,
                qualname: format!("{qualname}.{name}"),
                id: own.clone(),
                class_names: Some(bound.names()),
            });
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
