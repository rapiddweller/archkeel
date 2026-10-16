import json,subprocess
command=["uv","run","--locked","python","-m","archkeel.cli","validate","--root",".",
"--baseline","architecture-baseline.json","--against","4493b0a944e6caf0c56802c6333d9fd0090041b4",
"--amendment","docs/architecture/decisions/issue-542-method-descriptors-amendment.json","--json"]
result=subprocess.run(command,text=True,capture_output=True)
if result.stderr:print("REPLAY_STDERR",result.stderr[-4000:])
payload=json.loads(result.stdout)
print("DESCRIPTOR_FINAL_REPLAY",result.returncode,json.dumps({k:payload.get(k) for k in (
"exit_code","diagnostics","failures","widenings","amendment_status","measurements","declared_rules")},sort_keys=True))
assert result.returncode==0,payload
assert payload["amendment_status"]=="valid",payload
assert payload["failures"]==[] and payload["diagnostics"]==[],payload
assert payload["widenings"]==[],payload
subprocess.run(["git","diff","--exit-code"],check=True)
