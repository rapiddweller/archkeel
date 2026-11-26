// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one configuration, with the ids of each file resolved to text (AD-1047).

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

pub(crate) struct ImplFacts {
    pub(crate) module: String,
    pub(crate) tr: Option<String>,
    pub(crate) adts: Vec<String>,
    pub(crate) assoc: Vec<String>,
    /// The `dyn` traits of the associated types.
    pub(crate) assoc_dyns: Vec<String>,
    pub(crate) run: bool,
}

/// What a module, an opaque type or a coroutine holds: ADTs, `dyn` traits and opaque types.
pub(crate) struct Held {
    pub(crate) adts: Names,
    pub(crate) dyns: Names,
    pub(crate) opaques: Names,
}

pub(crate) type Names = BTreeSet<String>;

impl Held {
    pub(crate) fn new() -> Held {
        Held {
            adts: Names::new(),
            dyns: Names::new(),
            opaques: Names::new(),
        }
    }
}
/// For each scan module: its rustc modules, its generic functions and the indexes of its impls.
pub(crate) type Parts = BTreeMap<String, (Vec<String>, Vec<String>, Vec<usize>)>;

/// The facts of one configuration, with the ids of each file resolved to text and all units unioned.
pub struct Facts {
    pub(crate) mods: BTreeMap<String, Held>,
    pub(crate) fns: BTreeMap<String, (String, Option<String>)>,
    /// Type arguments (ADTs, `dyn` traits) that a call outside a generic function passes to a function.
    pub(crate) seeds: BTreeMap<String, (Names, Names)>,
    /// The flag: a type argument holds a parameter of the caller, so its instances flow too.
    pub(crate) edges: BTreeMap<(String, String), (Names, Names, bool)>,
    /// The `dyn` traits whose implementers the impls of the workspace do not list, each with the traits that a
    /// type needs to be one: auto traits (none), and each blanket impl in any crate.
    pub(crate) open: Vec<(String, Names)>,
    /// Opaque types (coroutines) of the sources of the casts to each `dyn` trait.
    pub(crate) coerce_opaque: BTreeMap<String, Names>,
    /// The supertraits of each `dyn` trait: a value can be upcast to them in code that no body shows.
    pub(crate) supers: BTreeMap<String, Names>,
    /// The modules, and the ADTs, whose types hold a raw pointer to `()` or `c_void`.
    pub(crate) erased: (Names, Names),
    /// The ADTs and `dyn` traits that a cast hid behind another type.
    pub(crate) lost: (Names, Names),
    /// For an ADT that holds an erased pointer (and `<ptr>`): the types that calls outside the workspace with it
    /// in their signature took in type arguments.
    pub(crate) via: BTreeMap<String, (Names, Names)>,
    pub(crate) coerce: BTreeMap<String, (Names, Names, Names)>,
    pub(crate) hidden: BTreeMap<String, Held>,
    pub(crate) adts: BTreeMap<String, (Names, Names)>,
    /// The `dyn` traits in the fields of ADTs of other crates (no `m` in their record). Only code that runs
    /// there can coerce a value to them, and that code gets its values from the workspace through calls.
    pub(crate) foreign_dyn: BTreeMap<String, Names>,
    pub(crate) impls: Vec<ImplFacts>,
    /// The crates for which this configuration built a `bin` target: the provenance of a `bin_<crate>` module.
    pub(crate) bins: Names,
}

fn blank<T: Default>() -> T {
    T::default()
}

fn one(v: &Value, key: &str, names: &[String]) -> Option<String> {
    let id = v.get(key)?.as_u64()?;
    names.get(usize::try_from(id).ok()?).cloned()
}

fn many(v: &Value, key: &str, names: &[String]) -> Names {
    let all = v.get(key).and_then(Value::as_array);
    let ids = all.into_iter().flatten().filter_map(Value::as_u64);
    ids.filter_map(|id| names.get(usize::try_from(id).ok()?).cloned())
        .collect()
}

impl Facts {
    /// No facts.
    pub fn empty() -> Facts {
        Facts {
            mods: blank(),
            fns: blank(),
            seeds: blank(),
            edges: blank(),
            open: blank(),
            coerce_opaque: blank(),
            supers: blank(),
            erased: blank(),
            lost: blank(),
            via: blank(),
            foreign_dyn: blank(),
            coerce: blank(),
            hidden: blank(),
            adts: blank(),
            impls: blank(),
            bins: blank(),
        }
    }

    /// Read each `*.jsonl` file of `dir`. A test unit that was merged into its library file has no records.
    pub fn load_dir(dir: &Path) -> Option<Facts> {
        let mut facts = Facts::empty();
        for entry in std::fs::read_dir(dir).ok()? {
            let path = entry.ok()?.path();
            if path.extension().is_some_and(|ext| ext == "jsonl") {
                facts.absorb(&std::fs::read_to_string(path).ok()?)?;
            }
        }
        Some(facts)
    }

    /// One `adt` record. A record without `m` (`local` false) is an ADT of another crate.
    fn adt(&mut self, name: String, (fields, dyns): (Names, Names), local: bool) {
        let held = if local {
            &mut self.adts.entry(name.clone()).or_default().1
        } else {
            self.foreign_dyn.entry(name.clone()).or_default()
        };
        held.extend(dyns);
        self.adts.entry(name).or_default().0.extend(fields);
    }

    pub(crate) fn absorb(&mut self, text: &str) -> Option<()> {
        let lines: Vec<&str> = text.lines().collect();
        let build: Option<Value> = lines.first().and_then(|l| serde_json::from_str(l).ok());
        if let Some(build) = &build {
            let kinds = build.get("crate_types").and_then(Value::as_array);
            let bin = kinds.is_some_and(|all| all.iter().any(|t| t.as_str() == Some("bin")));
            let krate = build.get("crate").and_then(Value::as_str);
            self.bins.extend(krate.filter(|_| bin).map(str::to_owned));
        }
        let table: Value = serde_json::from_str(lines.get(1)?).ok()?;
        // A test unit that was merged into its library file has `merged` here and no records.
        if table.get("k")?.as_str()? == "merged" {
            return Some(());
        }
        let names: Vec<String> = table
            .get("v")?
            .as_array()?
            .iter()
            .filter_map(|s| s.as_str().map(str::to_string))
            .collect();
        for line in lines.get(2..)? {
            let v: Value = serde_json::from_str(line).ok()?;
            self.record(&v, &names)?;
        }
        Some(())
    }

    /// The facts of the code and of the generic flow: modules, functions, calls, casts, hidden types.
    fn record(&mut self, v: &Value, names: &[String]) -> Option<()> {
        let kind = v.get("k")?.as_str()?;
        let (one, many) = (|k: &str| one(v, k, names), |k: &str| many(v, k, names));
        match kind {
            "mod" => {
                let entry = self.mods.entry(one("m")?).or_insert_with(Held::new);
                entry.adts.extend(many("mentions"));
                entry
                    .dyns
                    .extend(many("dyn").into_iter().chain(many("dyn_in")));
                entry.opaques.extend(many("opaque"));
                self.erased.0.extend(one("m").filter(|_| erased_flag(v)));
            }
            "fn" => {
                self.fns.insert(one("f")?, (one("m")?, one("implements")));
            }
            "seed" => {
                let s = self.seeds.entry(one("to")?).or_default();
                s.0.extend(many("args"));
                s.1.extend(many("dyn"));
            }
            "edge" => {
                let e = self.edges.entry((one("from")?, one("to")?)).or_default();
                e.0.extend(many("args"));
                e.1.extend(many("dyn"));
                e.2 |= v.get("param").and_then(Value::as_bool).unwrap_or(true);
            }
            "coerce" => {
                let c = self.coerce.entry(one("tr")?).or_default();
                c.0.extend(many("src"));
                c.1.extend(many("src_dyn"));
                c.2.extend(many("param_in"));
                self.coerce_opaque
                    .entry(one("tr")?)
                    .or_default()
                    .extend(many("src_opaque"));
            }
            "opaque" => {
                let h = self.hidden.entry(one("d")?).or_insert_with(Held::new);
                h.adts.extend(many("hidden"));
                h.dyns.extend(many("dyn"));
                h.opaques.extend(many("opaque"));
            }
            _ => return self.item(v, names),
        }
        Some(())
    }

    /// The facts of types and traits: ADTs, impls, supertraits, open traits, hidden pointers.
    fn item(&mut self, v: &Value, names: &[String]) -> Option<()> {
        let (one, many) = (|k: &str| one(v, k, names), |k: &str| many(v, k, names));
        match v.get("k")?.as_str()? {
            "adt" => {
                let name = one("d")?;
                let hidden = erased_flag(v);
                self.erased.1.extend(hidden.then(|| name.clone()));
                self.adt(name, (many("fields"), many("dyn")), v.get("m").is_some());
            }
            "impl" => self.impls.push(ImplFacts {
                module: one("m")?,
                tr: one("trait"),
                adts: many("self_adts").into_iter().collect(),
                assoc: many("assoc").into_iter().collect(),
                assoc_dyns: many("assoc_dyn").into_iter().collect(),
                run: v.get("run").and_then(Value::as_bool).unwrap_or(true),
            }),
            "super" => {
                let sups = self.supers.entry(one("tr")?).or_default();
                sups.extend(many("sup"));
            }
            "via" => {
                let e = self.via.entry(one("e")?).or_default();
                e.0.extend(many("adts"));
                e.1.extend(many("dyn"));
            }
            "lost" => {
                self.lost.0.extend(many("adts"));
                self.lost.1.extend(many("dyn"));
            }
            "open" => self.open.push((one("tr")?, many("needs"))),
            _ => {}
        }
        Some(())
    }
}

/// The record says that its types hold a raw pointer to `()` or `c_void`.
fn erased_flag(record: &Value) -> bool {
    record.get("erased").and_then(Value::as_bool) == Some(true)
}
