// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Fields retain insertion order; methods contribute property and mutation facts.

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
        json!({"name":self.name,"annotation":self.annotation,"binding":self.binding,"referent_mutability":self.referent,
            "mutability":self.mutability,"evidence_ids":self.evidence,"property_assignment":self.property})
    }
}

struct Class<'a> {
    module: &'a Module,
    qualified: &'a str,
    frozen: bool,
    protocol: bool,
    fields: Vec<Field>,
    positions: HashMap<String, usize>,
    methods: Vec<String>,
    properties: Vec<(String, bool)>,
    property_positions: HashMap<String, usize>,
    mutable: BTreeSet<String>,
    evidence: EvidenceMap,
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
    let mut class = Class {
        module,
        qualified,
        frozen,
        protocol,
        fields: Vec::new(),
        positions: HashMap::new(),
        methods: Vec::new(),
        properties: Vec::new(),
        property_positions: HashMap::new(),
        mutable: BTreeSet::new(),
        evidence: EvidenceMap::new(),
    };
    for child in &node.body {
        scan.tick(1)?;
        class.statement(scan, child)?;
    }
    class.finish(scan, evidence)
}

impl Class<'_> {
    fn field(&mut self, name: &str, frozen: bool) -> Result<&mut Field> {
        let index = match self.positions.get(name) {
            Some(index) => *index,
            None => {
                let index = self.fields.len();
                self.positions.insert(name.into(), index);
                self.fields.push(Field::new(name, frozen));
                index
            }
        };
        self.fields
            .get_mut(index)
            .ok_or_else(|| "state field position unseen".into())
    }

    fn statement(&mut self, scan: &mut Scan, child: &Stmt) -> Result<()> {
        if let Stmt::AnnAssign(n) = child {
            if let Expr::Name(name) = &*n.target {
                let mut field = Field::new(name.id.as_str(), self.frozen);
                field.annotate(
                    text(scan, self.module, Some(&n.annotation))?,
                    self.module.evidence(&mut self.evidence, n),
                );
                *self.field(name.id.as_str(), self.frozen)? = field;
            }
        }
        let Stmt::FunctionDef(n) = child else {
            return Ok(());
        };
        self.methods
            .push(scan.owner(self.qualified, n.name.as_str())?.to_string());
        self.decorators(scan, n)?;
        self.method_nodes(scan, child, n.name.as_str() == "__init__")
    }

    fn decorators(&mut self, scan: &mut Scan, n: &ruff_python_ast::StmtFunctionDef) -> Result<()> {
        let mut decorators = Vec::new();
        for d in &n.decorator_list {
            scan.tick(1)?;
            let target = match &d.expression {
                Expr::Call(n) => &*n.func,
                n => n,
            };
            if let Some(name) = text(scan, self.module, Some(target))? {
                decorators.push(name);
            }
        }
        decorators.sort();
        scan.tick(decorators.len())?;
        if decorators.iter().any(|d| d == "property") {
            self.property(n.name.as_str(), false)?;
        }
        for d in decorators {
            scan.tick(1)?;
            if let Some(name) = d.strip_suffix(".setter") {
                self.property(name, true)?;
            }
        }
        Ok(())
    }

    fn property(&mut self, name: &str, setter: bool) -> Result<()> {
        if let Some(index) = self.property_positions.get(name) {
            self.properties
                .get_mut(*index)
                .ok_or("property position unseen")?
                .1 = setter;
        } else {
            self.property_positions
                .insert(name.into(), self.properties.len());
            self.properties.push((name.into(), setter));
        }
        Ok(())
    }

    fn method_nodes(&mut self, scan: &mut Scan, child: &Stmt, initializer: bool) -> Result<()> {
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
            let Node::Expr(expr) = descendant else {
                continue;
            };
            self.attribute(scan, expr, &annotated, initializer)?;
            if let Some(name) = mutated(expr) {
                self.mutable.insert(name.into());
            }
        }
        Ok(())
    }

    fn attribute(
        &mut self,
        scan: &mut Scan,
        expr: &Expr,
        annotated: &HashMap<*const Expr, &ruff_python_ast::StmtAnnAssign>,
        initializer: bool,
    ) -> Result<()> {
        let Expr::Attribute(n) = expr else {
            return Ok(());
        };
        if !matches!(&*n.value,Expr::Name(n) if n.id.as_str()=="self") {
            return Ok(());
        }
        let index = match self.positions.get(n.attr.as_str()) {
            Some(index) => *index,
            None => {
                self.field(n.attr.as_str(), self.frozen)?;
                *self
                    .positions
                    .get(n.attr.as_str())
                    .ok_or("state field position unseen")?
            }
        };
        let field = self
            .fields
            .get_mut(index)
            .ok_or("state field position unseen")?;
        if field.evidence.is_empty() {
            field
                .evidence
                .push(self.module.evidence(&mut self.evidence, n));
        }
        if let Some(parent) = annotated.get(&std::ptr::from_ref(expr)) {
            field.annotate(
                text(scan, self.module, Some(&parent.annotation))?,
                self.module.evidence(&mut self.evidence, *parent),
            );
        }
        if n.ctx == ExprContext::Store && !initializer {
            self.mutable.insert(n.attr.to_string());
        }
        Ok(())
    }

    fn finish(mut self, scan: &mut Scan, evidence: &mut EvidenceMap) -> Result<Value> {
        for (name, setter) in std::mem::take(&mut self.properties) {
            scan.tick(1)?;
            self.field(&name, false)?.property =
                Some(if setter { "available" } else { "unavailable" });
        }
        for name in std::mem::take(&mut self.mutable) {
            scan.tick(1)?;
            self.field(&name, false)?.mutability = "mutable";
        }
        let mut values = Vec::new();
        for field in self.fields {
            scan.tick(1)?;
            scan.keep(&mut values, field.value())?;
        }
        scan.tick(self.evidence.len())?;
        let ids: Vec<_> = self.evidence.keys().cloned().collect();
        evidence.extend(self.evidence);
        Ok(
            json!({"qualified_name":self.qualified,"module":self.module.name,"frozen":self.frozen,
            "protocol":self.protocol,"fields":values,"methods":self.methods,"evidence_ids":ids}),
        )
    }
}

fn mutated(expr: &Expr) -> Option<&str> {
    let Expr::Call(call) = expr else {
        return None;
    };
    let Expr::Attribute(method) = &*call.func else {
        return None;
    };
    let Expr::Attribute(receiver) = &*method.value else {
        return None;
    };
    (matches!(&*receiver.value,Expr::Name(n) if n.id.as_str()=="self")
        && mutating(method.attr.as_str()))
    .then_some(receiver.attr.as_str())
}
