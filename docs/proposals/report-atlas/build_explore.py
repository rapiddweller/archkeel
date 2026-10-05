# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build one atlas dataset from an Archkeel report: Target components, observed component
edges, module weights and edges, and deterministic exploration hints per level.

Hints are questions for a human, never verdicts; each carries its evidence counts.
Mockup reference for #355 only: the product computes this in Core, not in the renderer.

Usage: python build_explore.py architecture.json architecture.report.html OUT.json STDOUT.json NAME
where STDOUT.json is the output of `archkeel report --json`.
"""

import json
import statistics
import sys
from collections import Counter, defaultdict

report_json, report_html, out, stdout_json, name = sys.argv[1:6]

# --- Target components and requires, from the report's embedded flow data ---
h = open(report_html, encoding="utf-8").read()
tag = '<script id="flow-data" type="application/json">'
s = h.find(tag) + len(tag)
t = json.loads(h[s : h.find("</script>", s)])["target"]
ent = {x["id"]: x for x in t["entities"]}
comps = []
for c in t["component_intents"]:
    en = ent.get(c["component_id"], {})
    comps.append(
        dict(
            id=c["component_id"],
            label=c["label"],
            parent=c["parent_id"],
            pkgs=c["packages"],
            resp=en.get("responsibilities") or [],
            excl=c["forbidden_responsibilities"],
            pub=c["public"],
            by=c["decided_by"],
            exact=c.get("exact_modules") or [],
        )
    )
C = {c["id"]: c for c in comps}
reqs = [
    dict(s=r["source_id"], t=r["target_id"], why=r["reason"], via=r["through"], by=r["decided_by"])
    for r in t["relationships"]
    if r["kind"] == "requires" and r["source_id"] in C and r["target_id"] in C
]

# --- Observed modules and module edges (columnar IR) ---
d = json.load(open(report_json))
st, enc = d["string_table"], d["encoding"]["section_data_fields"]


def sv(v):
    if isinstance(v, str) and v.startswith("$"):
        if v == "$m":
            return None
        if v.startswith("$$"):
            return v[1:]
        return st[int(v[1:])]
    return v


def rows(sec):
    for r in d[sec]:
        yield dict(zip(enc[sec], [sv(x) for x in r[10]], strict=True))


mods = {
    m["qualified_name"]: dict(
        sym=m["symbol_count"], fi=m["fan_in"], fo=m["fan_out"], rank=m["rank"]
    )
    for m in rows("modules")
}
medges = [
    (e["source"], e["target"], e["count"])
    for e in rows("dependency_edges")
    if e["level"] == "module" and e["source"] in mods and e["target"] in mods
]


# --- Ownership: deepest declared package prefix ---
def path(cid):
    p = []
    while cid:
        p.insert(0, cid)
        cid = C[cid]["parent"]
    return p


owners = sorted(
    ((pk, c["id"]) for c in comps for pk in c["pkgs"]), key=lambda x: (len(x[0]), len(path(x[1])))
)
exact = {m: c["id"] for c in comps for m in c["exact"]}
own = {}
for m in mods:
    best = None
    for pk, cid in owners:
        if m == pk or m.startswith(pk + "."):
            best = cid
    own[m] = exact.get(m, best)
for m, v in mods.items():
    v["own"] = own[m]
unowned = sorted(m for m in mods if own[m] is None)


def split(a, b):
    """Level and sibling pair where two owners diverge, or None when one contains the other."""
    pa, pb = path(a), path(b)
    i = 0
    while i < min(len(pa), len(pb)) and pa[i] == pb[i]:
        i += 1
    if i == len(pa) or i == len(pb):
        return None
    return (pa[i - 1] if i else "ROOT", pa[i], pb[i])


obs = Counter()
for a, b, n in medges:
    if own[a] and own[b] and own[a] != own[b]:
        sp = split(own[a], own[b])
        if sp:
            obs[sp] += n
o = [[p, s_, t_, n] for (p, s_, t_), n in sorted(obs.items())]

# --- Signals per level ---
importers = defaultdict(list)
for a, b, n in medges:
    importers[b].append((a, n))
top = {cid: path(cid)[0] for cid in C}
levels = ["ROOT"] + [c["id"] for c in comps]


def in_level(m, lvl):
    return lvl == "ROOT" or (own[m] is not None and lvl in path(own[m]))


signals = {}
for lvl in levels:
    ms = [m for m in mods if in_level(m, lvl)]
    if len(ms) < 2:
        continue
    sig = []
    # Hubs: many modules depend on it; a change ripples.
    hubs = sorted((m for m in ms if mods[m]["fi"] >= 10), key=lambda m: (-mods[m]["fi"], m))[:3]
    for m in hubs:
        users = Counter(top[own[a]] for a, _ in importers[m] if own[a])
        sig.append(
            dict(
                k="hub",
                m=m,
                n=mods[m]["fi"],
                ev=f"Imported by {mods[m]['fi']} modules from {len(users)} top-level "
                f"component{'' if len(users) == 1 else 's'}: "
                + ", ".join(f"{C[u]['label']} {k}" for u, k in users.most_common()),
                q="Is this the intended shared kernel, "
                "or has it become a catch-all that every change touches?",
            )
        )
    # Single outside consumer across top-level boundaries, grouped so one question covers all.
    groups = defaultdict(list)
    for m in sorted(ms):
        if not own[m] or not importers[m]:
            continue
        users = {top[own[a]] for a, _ in importers[m] if own[a]}
        if len(users) == 1 and top[own[m]] not in users:
            groups[(top[own[m]], users.pop())].append(m)
    for (ot, ut), group in sorted(groups.items()):
        k = sum(n for m in group for _, n in importers[m])
        names = ", ".join(m.rsplit(".", 1)[-1] for m in group)
        o_, u_, verb = C[ot]["label"], C[ut]["label"], "s are" if len(group) > 1 else " is"
        sig.append(
            dict(
                k="single",
                m=group[0],
                ms=group,
                n=k,
                ev=f"{len(group)} {o_} module{verb} used only by {u_} ({k} imports): {names}.",
                q=f"Do they belong to {u_}, or are they {o_}'s intended interface for {u_}?",
            )
        )
    # Weight outliers inside this level.
    syms = [mods[m]["sym"] for m in ms if mods[m]["sym"]]
    med = statistics.median(syms) if syms else 0
    for m in sorted(
        (m for m in ms if med and mods[m]["sym"] >= max(40, 3 * med)), key=lambda m: -mods[m]["sym"]
    )[:3]:
        sig.append(
            dict(
                k="weight",
                m=m,
                n=mods[m]["sym"],
                ev=f"{mods[m]['sym']} symbols, "
                f"{mods[m]['sym'] / med:.1f}x the median module here ({med:g}).",
                q="One responsibility, or several that grew together?",
            )
        )
    if lvl == "ROOT":
        for m in unowned:
            sig.append(
                dict(
                    k="unowned",
                    m=m,
                    n=0,
                    ev="No component declares this module.",
                    q="Which component owns it, or is it a namespace container?",
                )
            )
    # Single-consumer hints are the most specific; keep them first, then hubs, weight, ownership.
    order = {"single": 0, "hub": 1, "weight": 2, "unowned": 3}
    signals[lvl] = sorted(sig, key=lambda x: (order[x["k"]], -x["n"], x["m"]))

# --- Verdict summary and per-component status from the report's rule assessments ---
so = json.load(open(stdout_json))
bypath = {tuple(C[x]["label"] for x in path(c["id"])): c["id"] for c in comps}
rank_ = {"PASS": 0, "UNKNOWN": 1, "FAIL": 2}
own_status = {}
for ra in so["rule_assessments"]:
    if ra["status"] == "PASS":
        continue
    if ra["scope"] == "root":
        targets = [bypath[(lab,)] for lab in ra["components"] if (lab,) in bypath]
    else:
        targets = (
            [bypath[tuple(ra["scope"].split(":"))]]
            if tuple(ra["scope"].split(":")) in bypath
            else []
        )
    if ra["status"] == "FAIL":
        why = f"{ra['id']}: {ra['count']} violation{'' if ra['count'] == 1 else 's'}"
    elif ra.get("undecided"):
        why = (
            f"{ra['id']}: {ra['undecided']} position{'' if ra['undecided'] == 1 else 's'} undecided"
        )
    else:
        why = f"{ra['id']}: {ra['reason']}"
    for cid in targets:
        own_status.setdefault(cid, []).append((ra["status"], why))
status = {}
for cid, items in own_status.items():
    worst = max(items, key=lambda x: rank_[x[0]])[0]
    status[cid] = [worst, [w for s_, w in items if s_ == worst]]
# Ancestors show the worst status inside them, so a parent never reads PASS over a failing child.
for cid in list(own_status):
    for anc in path(cid)[:-1]:
        cur = status.get(anc)
        inner = status[cid][0]
        if not cur or rank_[inner] > rank_[cur[0]]:
            status[anc] = [inner, [f"inside: {C[cid]['label']}"]]
        elif (
            cur[0] == inner
            and f"inside: {C[cid]['label']}" not in cur[1]
            and not any(not w.startswith("inside") for w in cur[1])
        ):
            cur[1].append(f"inside: {C[cid]['label']}")
cov, sc = so["coverage"], so["measurements"]["scalars"]
ras = so["rule_assessments"]
meta = dict(
    name=name,
    scan=cov["status"],
    parsed=cov["files_parsed"],
    discovered=cov["files_discovered"],
    rules=so["declared_rules"],
    rules_total=len(ras),
    rules_open=sum(r["status"] != "PASS" for r in ras),
    violations=sc["violations"],
    unknown_positions=sc["unknown_positions"],
    decisions=so["agent_decisions"],
    levels=max(len(path(c["id"])) for c in comps) + 1,
    status=status,
    files=len(mods),
    components=len(comps),
    requires=len(reqs),
    agent_components=sum(c["by"] == "agent" for c in comps),
    agent_requires=sum(r["by"] == "agent" for r in reqs),
    module_edges=len(medges),
    git=d["source"]["git_head"][:7],
)
json.dump(
    dict(
        meta=meta,
        c=comps,
        r=reqs,
        o=o,
        unowned={"ROOT": unowned},
        mods={
            m: [v["sym"], v["fi"], v["fo"], v["rank"], v["own"]] for m, v in sorted(mods.items())
        },
        medges=sorted(medges),
        signals=signals,
    ),
    open(out, "w"),
    separators=(",", ":"),
)
print(
    json.dumps(meta),
    "observed comp edges",
    len(o),
    "unowned",
    len(unowned),
    "signals",
    {k: len(v) for k, v in signals.items() if v},
)
