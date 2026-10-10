"""Exercise the actual experiment manager and SSH bridge without paid traffic."""
import asyncio
import base64
import json
import re
from types import SimpleNamespace
import urllib.request
from ai_scientist.workbench.agents.contracts import RuntimeRequest
from ai_scientist.workbench.models import SearchOptions
from test_working import fixture

class SearchRuntime:
    def __init__(self):
        self.calls=[]
        self.search_options=SearchOptions(stage_iterations=[1,1,1,1],debug_prob=0)
        self.spec=SimpleNamespace(execution_seconds=180)

    def run(self,request,progress,cancelled):
        self.calls.append(request)
        if request.role=='mvp1_search_query':
            data=json.loads((request.workdir/'query-request.json').read_text())
            spec=data.get('function')
            if not spec:
                response='Verified local fixture analysis'
            else:
                def value(schema):
                    if 'enum' in schema: return schema['enum'][0]
                    kind=schema.get('type')
                    if kind=='boolean': return True
                    if kind in {'integer','number'}: return 1
                    if kind=='array': return []
                    if kind=='object': return {k:value(v) for k,v in schema.get('properties',{}).items() if k in schema.get('required',[])}
                    return 'fixture'
                body=value(spec['json_schema'])
                if spec['name']=='select_best_implementation':
                    candidates=re.findall(r'ID: ([0-9a-f]{32})',str(data['system_message']))
                    for name in body:
                        if 'id' in name: body[name]=candidates[0]
                response=json.dumps(body)
            return SimpleNamespace(text=json.dumps({'response':response}),files={})
        assert request.role=='mvp1_search_node'
        access=json.loads((request.workdir/'terminal-access.json').read_text())
        def call(action,**kw):
            wire=urllib.request.Request(access['url'],json.dumps({'action':action,**kw}).encode(),
                {'Authorization':'Bearer '+access['token'],'Content-Type':'application/json'})
            with urllib.request.urlopen(wire,timeout=5) as response:
                return json.loads(response.read())
        call('exec',command='python source/workload.py',timeout=2)
        call('write',path='source/workload.py',data=base64.b64encode(b'print("fixture")\n').decode())
        call('write',path='output/metric.json',data=base64.b64encode(b'{"value":0.25}').decode())
        return SimpleNamespace(text=json.dumps({'succeeded':True,'summary':'Measured fixture result','plan':'Run the fixture',
            'limitations':['Local fixture only'],'output_files':['output/metric.json'],
            'metric':{'name':'EMD','value':.25,'direction':'minimize','evidence_file':'output/metric.json','evidence_pointer':'/value'},
            'datasets_tested':['fixture']}),files={})

def test_configured_workflow_reuses_original_four_stage_manager(tmp_path,monkeypatch):
    async def check():
        monkeypatch.chdir(tmp_path)
        runtime=SearchRuntime()
        store,project,run,worker,planner,working,_,bootstrap,donor=fixture(tmp_path,runtime=runtime)
        planner.bindings.request_type=RuntimeRequest
        working.config.codex_model='fixture'
        try:
            await working.start(project,run)
            await working.tasks[project,run]
            detail=working.detail(project,run)
            assert detail['state']=='COMPLETED',detail
            assert detail['working']['stop_confirmed']
            node_stages=[r.stage for r in runtime.calls if r.role=='mvp1_search_node']
            assert node_stages==['draft','tuning','research','ablation']
            assert len(bootstrap.calls)==len(donor.opens)==1
            root=working.view.root(project,run)
            state=json.loads((root/'logs/0-run/search-state.json').read_text())
            assert len(state['stages'])==4
            assert (root/'output/metric.json').is_file()
        finally:
            await working.close(2)
            await planner.close()
            await worker.close(2)
    asyncio.run(check())
