// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Field insertion order, property assignment and source-only class mutation signals.

use super::*;

struct Field {
    name: String,
    annotation: Option<String>,
    binding: &'static str,
    referent: &'static str,
    mutability: &'static str,
    evidence: Vec<String>,
    property: Option<&'static str>,
}

impl Field {
    fn new(name: &str, frozen: bool) -> Self {
        Self {
            name: name.into(),
            annotation: None,
            binding: "UNKNOWN",
            referent: "UNKNOWN",
            mutability: if frozen {
                "object_immutable"
            } else {
                "UNKNOWN"
            },
            evidence: Vec::new(),
            property: None,
        }
    }

    fn annotate(&mut self, annotation: Option<String>, evidence: String) {
        if annotation.as_ref().is_some_and(|a| {
            matches!(a.as_str(), "Final" | "typing.Final")
                || a.starts_with("Final[")
                || a.starts_with("typing.Final[")
        }) {
            self.binding = "non_reassignable";
        }
        if annotation.as_ref().is_some_and(|a| {
            ["list[", "dict[", "set[", "List[", "Dict[", "Set["]
                .iter()
                .any(|s| a.contains(s))
        }) {
            self.referent = "mutable_container";
        }
        self.annotation = annotation;
        self.evidence = vec![evidence];
    }

    fn value(self) -> Value {
        json!({"name": self.name, "annotation": self.annotation, "binding": self.binding,
            "referent_mutability": self.referent, "mutability": self.mutability,
            "evidence_ids": self.evidence, "property_assignment": self.property})
    }
}

fn field<'a>(
    fields: &'a mut Vec<Field>,
    positions: &mut HashMap<String, usize>,
    name: &str,
    frozen: bool,
) -> Result<&'a mut Field> {
    let index = match positions.get(name) {
        Some(index) => *index,
        None => {
            let index = fields.len();
            positions.insert(name.into(), index);
            fields.push(Field::new(name, frozen));
            index
        }
    };
    fields
        .get_mut(index)
        .ok_or_else(|| "state field position unseen".into())
}

#[allow(clippy::too_many_arguments)]
pub(super) fn collect(
    scan: &mut Scan,
    module: &Module,
    qualified: &str,
    node: &StmtClassDef,
    frozen: bool,
    protocol: bool,
    evidence: &mut EvidenceMap,
) -> Result<Value> {
    let mut local = EvidenceMap::new();
    let mut fields = Vec::new();
    let mut positions = HashMap::new();
    let mut methods = Vec::new();
    let mut properties = Vec::new();
    let mut property_positions = HashMap::new();
    let mut mutable = BTreeSet::new();
    for child in &node.body {
        scan.tick(1)?;
        if let Stmt::AnnAssign(n) = child {
            if let Expr::Name(name) = &*n.target {
                let mut fresh = Field::new(name.id.as_str(), frozen);
                fresh.annotate(
                    text(scan, module, Some(&n.annotation))?,
                    module.evidence(&mut local, n),
                );
                *field(&mut fields, &mut positions, name.id.as_str(), frozen)? = fresh;
            }
        }
        let Stmt::FunctionDef(n) = child else {
            continue;
        };
        let owner = scan.owner(qualified, n.name.as_str())?;
        methods.push(owner.to_string());
        let mut decorators = Vec::new();
        for d in &n.decorator_list {
            scan.tick(1)?;
            let target = match &d.expression {
                Expr::Call(n) => &*n.func,
                n => n,
            };
            if let Some(name) = text(scan, module, Some(target))? {
                decorators.push(name);
            }
        }
        decorators.sort();
        scan.tick(decorators.len())?;
        if decorators.iter().any(|d| d == "property") {
            property(
                &mut properties,
                &mut property_positions,
                n.name.as_str(),
                false,
            )?;
        }
        for d in decorators {
            scan.tick(1)?;
            if let Some(name) = d.strip_suffix(".setter") {
                property(&mut properties, &mut property_positions, name, true)?;
            }
        }
        let descendants = scan.walk(Node::Stmt(child))?;
        let mut annotated = HashMap::new();
        for n in &descendants {
            scan.tick(1)?;
            if let Node::Stmt(Stmt::AnnAssign(n)) = n {
                annotated.insert(std::ptr::from_ref(&*n.target), n);
            }
        }
        for descendant in descendants {
            scan.tick(1)?;
            if let Node::Expr(expr @ Expr::Attribute(a)) = &descendant {
                if matches!(&*a.value, Expr::Name(n) if n.id.as_str() == "self") {
                    let field = field(&mut fields, &mut positions, a.attr.as_str(), frozen)?;
                    if field.evidence.is_empty() {
                        field.evidence.push(module.evidence(&mut local, a));
                    }
                    if let Some(parent) = annotated.get(&std::ptr::from_ref(*expr)) {
                        field.annotate(
                            text(scan, module, Some(&parent.annotation))?,
                            module.evidence(&mut local, *parent),
                        );
                    }
                    if a.ctx == ExprContext::Store && n.name.as_str() != "__init__" {
                        mutable.insert(a.attr.to_string());
                    }
                }
            }
            if let Node::Expr(Expr::Call(c)) = descendant {
                if let Expr::Attribute(a) = &*c.func {
                    if let Expr::Attribute(receiver) = &*a.value {
                        if matches!(&*receiver.value, Expr::Name(n) if n.id.as_str() == "self")
                            && mutating(a.attr.as_str())
                        {
                            mutable.insert(receiver.attr.to_string());
                        }
                    }
                }
            }
        }
    }
    for (name, setter) in properties {
        scan.tick(1)?;
        field(&mut fields, &mut positions, &name, false)?.property =
            Some(if setter { "available" } else { "unavailable" });
    }
    for name in mutable {
        scan.tick(1)?;
        field(&mut fields, &mut positions, &name, false)?.mutability = "mutable";
    }
    let mut values = Vec::new();
    for field in fields {
        scan.tick(1)?;
        scan.keep(&mut values, field.value())?;
    }
    scan.tick(local.len())?;
    let ids: Vec<_> = local.keys().cloned().collect();
    evidence.extend(local);
    Ok(
        json!({"qualified_name": qualified, "module": module.name, "frozen": frozen,
        "protocol": protocol, "fields": values, "methods": methods, "evidence_ids": ids}),
    )
}

fn property(
    properties: &mut Vec<(String, bool)>,
    positions: &mut HashMap<String, usize>,
    name: &str,
    setter: bool,
) -> Result<()> {
    if let Some(index) = positions.get(name) {
        properties
            .get_mut(*index)
            .ok_or("property position unseen")?
            .1 = setter;
    } else {
        positions.insert(name.into(), properties.len());
        properties.push((name.into(), setter));
    }
    Ok(())
}
