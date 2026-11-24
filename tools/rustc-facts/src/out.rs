// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts file of one unit: the `build` line, the string table and the records (AD-1047).
//!
//! The file is JSON lines. Every id is an index in the string table of the same file.
//! Schema 1:
//!
//! - `build`: `schema`, `crate`, `unit`, `test`, `crate_types`, `rustc` (the text of `rustc -vV`),
//!   `driver_sha256`, `target_triple`, `cfg`, `cfg_args`, `cargo_lock_sha256`, and `files`:
//!   `[[path, sha256]]` for each source file that rustc read, with the hash that rustc made.
//! - `str`: `v`, the string table. `end`: `lines`, the number of lines before it; always the last line.
//! - `mod`: `m`, `file`, `mentions`, `dyn`, `opaque`, `dyn_in`: the type reach of one module.
//! - `fn`: `f`, `m`, `implements`: a generic function, with the bodies of its closures.
//! - `seed`: `to`, `args`; `edge`: `from`, `to`, `args`: type arguments of calls to a generic callee.
//! - `coerce`: `tr`, `src`, `src_dyn`, `param_in`: the source types of unsize casts to the `dyn` trait `tr`.
//!   `src_dyn` holds the `dyn` traits of the source (trait upcasting).
//! - `opaque`: `d`, `hidden`, `dyn`, `opaque` (opaque types and coroutines that the hidden type mentions). `adt`: `d`, `m`, `file`, `fields`, `dyn`.
//! - `impl`: `trait`, `self`, `self_adts`, `assoc`, `items`, `m`, `file`, `line`, `run`, `expansion`.

use crate::state::State;
use crate::{items, json};
use rustc_middle::ty::TyCtxt;
use std::io::Write;

/// The schema number. The reader refuses any other number.
const SCHEMA: u32 = 1;

/// What the driver knows about its unit before it compiles.
pub(crate) struct Unit {
    pub(crate) root: String,
    file: String,
    stem: String,
    krate: String,
    test: bool,
    crate_types: Vec<String>,
    cfg_args: Vec<String>,
    rustc_vv: String,
    target_triple: String,
    driver_sha256: String,
    lock_sha256: String,
    cfg: String,
    /// The canonical root source file of each target of the workspace members: only these crates are workspace code.
    pub(crate) members: std::collections::BTreeSet<String>,
}

fn env(name: &str) -> Option<String> {
    std::env::var(name).ok()
}

fn after(args: &[String], flag: &str) -> Vec<String> {
    let mut found = Vec::new();
    for w in args.windows(2) {
        if w[0] == flag {
            found.push(w[1].clone());
        }
    }
    found
}

/// The root with `/` separators and a closing slash, after symbolic links (macOS `/var` is `/private/var`).
fn canonical_root(root: &str) -> String {
    let real = std::fs::canonicalize(root)
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| root.to_string());
    format!("{}/", real.replace('\\', "/").trim_end_matches('/'))
}

/// The sysroot that `rustc` reports.
pub(crate) fn sysroot(rustc: &str) -> String {
    let out = std::process::Command::new(rustc)
        .args(["--print", "sysroot"])
        .output();
    out.map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

impl Unit {
    pub(crate) fn new(rustc: &str, args: &[String]) -> Option<Unit> {
        let dir = env("AK_FACTS_DIR")?;
        let krate = after(args, "--crate-name")
            .pop()
            .unwrap_or_else(|| "x".to_string());
        // The collector names a unit by the suffix of its `.rmeta` file, which is `extra-filename`.
        // `metadata` can differ from it, so it is only the fallback.
        let extra = args.iter().find_map(|a| a.strip_prefix("extra-filename=-"));
        let meta = extra
            .or_else(|| args.iter().find_map(|a| a.strip_prefix("metadata=")))
            .unwrap_or("")
            .to_string();
        let test = args.iter().any(|a| a == "--test");
        let stem = format!("{krate}-{meta}{}", if test { "-test" } else { "" });
        let vv = std::process::Command::new(rustc).arg("-vV").output().ok()?;
        let rustc_vv = String::from_utf8_lossy(&vv.stdout).to_string();
        let host = rustc_vv
            .lines()
            .find_map(|l| l.strip_prefix("host: "))
            .unwrap_or("")
            .to_string();
        Some(Unit {
            root: canonical_root(&env("AK_FACTS_ROOT")?),
            file: format!("{dir}/{stem}.jsonl"),
            stem,
            krate,
            test,
            crate_types: after(args, "--crate-type"),
            cfg_args: after(args, "--cfg"),
            rustc_vv,
            target_triple: after(args, "--target").pop().unwrap_or(host),
            driver_sha256: env("AK_FACTS_DRIVER_SHA256")?,
            lock_sha256: env("AK_FACTS_LOCK_SHA256")?,
            cfg: env("AK_FACTS_CFG")?,
            members: env("AK_FACTS_MEMBERS")?
                .split('\n')
                .filter(|m| !m.is_empty())
                .map(str::to_string)
                .collect(),
        })
    }
}

fn build_line(u: &Unit, files: &[(String, String)]) -> String {
    let pairs: Vec<String> = files
        .iter()
        .map(|(p, h)| format!("[{},{}]", json::text(p), json::text(h)))
        .collect();
    let mut cfg_args = u.cfg_args.clone();
    cfg_args.sort();
    format!(
        "{{\"k\":\"build\",\"schema\":{SCHEMA},\"crate\":{},\"unit\":{},\"test\":{},\"crate_types\":{},\"rustc\":{},\"driver_sha256\":{},\"target_triple\":{},\"cfg\":{},\"cfg_args\":{},\"cargo_lock_sha256\":{},\"files\":[{}]}}",
        json::text(&u.krate),
        json::text(&u.stem),
        u.test,
        json::texts(&u.crate_types),
        json::text(&u.rustc_vv),
        json::text(&u.driver_sha256),
        json::text(&u.target_triple),
        json::text(&u.cfg),
        json::texts(&cfg_args),
        json::text(&u.lock_sha256),
        pairs.join(",")
    )
}

/// The hash that rustc made of each real source file of this crate, in the source map.
fn source_files(tcx: TyCtxt<'_>, root: &str) -> Vec<(String, String)> {
    let mut files: Vec<(String, String)> = tcx
        .sess
        .source_map()
        .files()
        .iter()
        .filter(|f| !f.is_imported() && matches!(f.name, rustc_span::FileName::Real(_)))
        .map(|f| {
            let hash = f.src_hash.to_string();
            let sha = hash
                .strip_prefix("sha256=")
                .map(str::to_string)
                .unwrap_or(hash);
            (
                items::relative(root, &f.name.prefer_local_unconditionally().to_string()),
                sha,
            )
        })
        .collect();
    files.sort();
    files
}

/// Write the facts of the whole crate. A failure to write stops the build: no file means no facts.
pub(crate) fn write(u: &Unit, tcx: TyCtxt<'_>, st: &mut State) {
    let mut lines: Vec<String> = Vec::new();
    items::opaques(tcx, st, &mut lines);
    items::items(tcx, st, &mut lines);
    items::foreign(tcx, st, &mut lines);
    items::open(tcx, st, &mut lines);
    items::supers(tcx, st, &mut lines);
    items::close_erased(st);
    let ptr = st.names.text("<ptr>");
    for (key, flow) in &st.via {
        if *key == ptr || st.erased_adts.contains(key) {
            lines.push(format!(
                "{{\"k\":\"via\",\"e\":{key},\"adts\":{},\"dyn\":{}}}",
                json::ids(&flow.adts),
                json::ids(&flow.dyns)
            ));
        }
    }
    for (m, f) in &st.modules {
        lines.push(format!(
            "{{\"k\":\"mod\",\"m\":{m},\"file\":{},\"mentions\":{},\"dyn\":{},\"opaque\":{},\"dyn_in\":{},\"erased\":{}}}",
            f.file, json::ids(&f.mentions), json::ids(&f.dyns), json::ids(&f.opaques), json::ids(&f.dyn_in), f.erased
        ));
    }
    for (id, f) in &st.fns {
        let implements = f.implements.map_or("null".to_string(), |n| n.to_string());
        lines.push(format!(
            "{{\"k\":\"fn\",\"f\":{id},\"m\":{},\"implements\":{implements}}}",
            f.module
        ));
    }
    for (to, a) in &st.seeds {
        lines.push(format!(
            "{{\"k\":\"seed\",\"to\":{to},\"args\":{},\"dyn\":{}}}",
            json::ids(&a.adts),
            json::ids(&a.dyns)
        ));
    }
    for ((from, to), a) in &st.edges {
        lines.push(format!(
            "{{\"k\":\"edge\",\"from\":{from},\"to\":{to},\"args\":{},\"dyn\":{},\"param\":{}}}",
            json::ids(&a.adts),
            json::ids(&a.dyns),
            a.param
        ));
    }
    for (tr, c) in &st.coerce {
        lines.push(format!(
            "{{\"k\":\"coerce\",\"tr\":{tr},\"src\":{},\"src_dyn\":{},\"param_in\":{},\"src_opaque\":{}}}",
            json::ids(&c.adts),
            json::ids(&c.dyns),
            json::ids(&c.param_in),
            json::ids(&c.opaques)
        ));
    }
    lines.push(format!(
        "{{\"k\":\"lost\",\"adts\":{},\"dyn\":{}}}",
        json::ids(&st.cast_lost.adts),
        json::ids(&st.cast_lost.dyns)
    ));
    let strings = json::texts(st.names.list());
    let head = [
        build_line(u, &source_files(tcx, &u.root)),
        format!("{{\"k\":\"str\",\"v\":{strings}}}"),
    ];
    // The `end` record counts the lines before it, so a reader finds a cut-off file. The file is
    // written under another name and renamed, so a reader never sees half of it.
    let count = head.len() + lines.len();
    let temporary = format!("{}.tmp", u.file);
    let file = std::fs::File::create(&temporary).unwrap_or_else(|e| fail(&temporary, e));
    let mut w = std::io::BufWriter::new(file);
    for l in head.iter().chain(lines.iter()) {
        writeln!(w, "{l}").unwrap_or_else(|e| fail(&temporary, e));
    }
    writeln!(w, "{{\"k\":\"end\",\"lines\":{count}}}").unwrap_or_else(|e| fail(&temporary, e));
    w.flush().unwrap_or_else(|e| fail(&temporary, e));
    drop(w);
    std::fs::rename(&temporary, &u.file).unwrap_or_else(|e| fail(&u.file, e));
}

fn fail(file: &str, e: std::io::Error) -> ! {
    eprintln!("archkeel-rustc-facts: cannot write {file}: {e}");
    std::process::exit(2);
}
