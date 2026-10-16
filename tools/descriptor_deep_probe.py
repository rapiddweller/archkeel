import json,sys,subprocess,collections,re
from pathlib import Path
root=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(root/"src"))
mode=sys.argv[1]
if mode=="native":
    from archkeel.cli.observe import observer_for
    from archkeel.check.ports import Language
    from archkeel.ir.facts_codec import record_payload
    bootstrap="import sys;sys.path.insert(0,"+repr(str(root/"src"))+");from archkeel.analyzer.python.entry import main;raise SystemExit(main())"
    observed=observer_for(Language.PYTHON,collector_argv=(sys.executable,"-I","-B","-c",bootstrap))(
        root,roots=("src/archkeel",),namespace="archkeel",contract="architecture-contract.json",
        git_head="0"*40,dirty=False,contract_root=root)
    assert observed.diagnostics==() and observed.observation is not None,observed
    model=observed.observation
    def normalized(value):
        if isinstance(value,str):
            return re.sub(r"<(genexpr|listcomp|setcomp|dictcomp|lambda):\d+:\d+>",r"<\1>",value)
        if isinstance(value,list):return [normalized(x) for x in value]
        if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
        return value
    sections={}
    for name in ("calls","references"):
        rows=[]
        for item in model.records(name):
            data=record_payload(item)["data"]
            rows.append(normalized({key:data.get(key) for key in (
                "source_module","source_scope","expression","status","reason",
                "targets","candidate_count","candidates_truncated")}))
        sections[name]=rows
    sections["unknowns"]=[normalized({
        "id":item.id,"kind":item.kind,"subjects":list(item.subjects),
        "rule_ids":list(item.rule_ids),"data":record_payload(item)["data"]})
        for item in model.records("unknowns")]
    sections["typing_signals"]=[normalized({"kind":item.kind,"subjects":list(item.subjects),"data":record_payload(item)["data"]}) for item in model.records("typing_signals")]
    Path(sys.argv[3]).write_text(json.dumps(sections,sort_keys=True))
elif mode=="wire":
    from archkeel.ir.protocol import CollectionRequest,CollectionResponse,SnapshotInput,SourceScope,PythonSettings,DartSettings,TypeScriptSettings
    from archkeel.ir.facts_codec import encode_response,decode_response
    from archkeel.analyzer.python.collect import collect as python_collect
    from archkeel.analyzer.dart.collect import collect as dart_collect
    from archkeel.analyzer.typescript.collect import collect as typescript_collect
    fixtures=Path(sys.argv[3])
    payloads={}
    for name,roots,namespace,settings,collector in [
        ("python",("sample",),"sample",PythonSettings(),python_collect),
        ("dart",("lib",),"app",DartSettings(),dart_collect),
        ("typescript",("src",),"app",TypeScriptSettings(),typescript_collect)]:
        request=CollectionRequest(SnapshotInput(str(fixtures/name),"a"*40,False),SourceScope(roots,namespace),settings)
        facts=collector(request)
        wire=encode_response(CollectionResponse(facts))
        assert encode_response(decode_response(wire))==wire
        payload=json.loads(wire)
        payload["facts"]["adapter"]["code_digest"]="<source revision>"
        payloads[name]=payload
    Path(sys.argv[4]).write_text(json.dumps(payloads,sort_keys=True,separators=(",",":")))
else:raise AssertionError(mode)
