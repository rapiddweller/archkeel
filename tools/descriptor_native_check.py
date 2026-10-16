import base64,json,subprocess,sys
from pathlib import Path
base=sys.argv[1]
common=["uv","run","--locked","python","-m","archkeel.cli","validate","--root",".","--baseline","architecture-baseline.json","--json"]
def run(label,extra):
    result=subprocess.run(common+extra,text=True,capture_output=True)
    Path("/tmp/"+label+".json").write_text(result.stdout)
    try:
        payload=json.loads(result.stdout)
    except Exception:
        print(label,"NOT_JSON",result.returncode,result.stdout[-4000:],result.stderr[-4000:]);raise
    print(label,"EXIT",result.returncode,json.dumps({k:payload.get(k) for k in (
        "diagnostics","failures","widenings","amendment_status","measurements",
        "baseline_status","violations","comparison_status","declared_rules")},sort_keys=True))
    if result.stderr:print(label,"STDERR",result.stderr[-3000:])
    return result.returncode
run("DESCRIPTOR_NOWRITE",[])
path="docs/architecture/decisions/issue-542-method-descriptors-amendment.json"
code=run("DESCRIPTOR_WRITER",["--write-baseline","--against",base,"--amendment",path,"--write-amendment","--decided-by","Archkeel maintainers, authorized in issue #542","--rationale","Own five shared method kinds and descriptor proof in source facts, preserve raw wire compatibility and conservative receiver semantics, and pin consumed nominal APIs without increasing budgets."])
for label,filename in (("DESCRIPTOR_BASELINE","architecture-baseline.json"),("DESCRIPTOR_AMENDMENT",path)):
    file=Path(filename)
    if file.exists():print(label+"="+base64.b64encode(file.read_bytes()).decode())
raise SystemExit(code)
