"""Literature, original citation loop, and real image plumbing without paid calls."""
import base64
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import uuid

from PIL import Image
import pytest

from ai_scientist.workbench.models import ResearchPlan
from ai_scientist.workbench.research_client import CodexResearchClient
from ai_scientist.workbench.research_evidence import gather_citations, analyze_plots, review_pdf
from ai_scientist.workbench.research_images import detach_images
from ai_scientist.workbench.research_literature import LiteratureSearch, review_idea
from ai_scientist.workbench.store import StoreConflict
from ai_scientist.workbench.workflow_models import WorkflowSpec
from tests.workbench.test_agent_team_execution import repository


PAPER = {'paperId':'verified-paper','title':'Verified baseline','authors':[{'name':'Researcher'}],
         'venue':'A conference','year':2025,'abstract':'Tests the baseline method.', 'citationCount':3,
         'url':'https://www.semanticscholar.org/paper/verified-paper',
         'citationStyles':{'bibtex':'@article{Verified2025,\n title = {Verified baseline},\n year = {2025}\n}'}}


def search_fixture(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:{'data':[PAPER]})
    monkeypatch.setattr('ai_scientist.workbench.research_literature.requests.get',get)
    return calls


@pytest.mark.parametrize('novel',[True,False])
def test_literature_requires_retrieved_evidence_and_persists_verdict(tmp_path,monkeypatch,novel):
    calls = search_fixture(monkeypatch)
    events = []
    actions = iter([{'action':'search','query':'baseline method','reason':'Check nearest work'},
        {'action':'finalize','novel':novel,'reason':'The intervention differs from the retrieved baseline',
         'title':'Intervention','text':'Measure the intervention on the pinned split','related_work':'Verified baseline is the comparison'}])
    runtime = SimpleNamespace(project='p',workflow='w',check=lambda:None,
        spec=SimpleNamespace(goal='Compare intervention',research=ResearchPlan(literature=True,literature_rounds=2)),
        owner=SimpleNamespace(projects=SimpleNamespace(directory=lambda _:tmp_path,workspace=tmp_path),
            store=SimpleNamespace(get=lambda *_:{'state':{'iteration':0}},event=lambda *args,**kw:events.append(args))),
        invoke=lambda *args,**kwargs:next(actions))
    if novel:
        result = review_idea(runtime,{'title':'Intervention','text':'Measure intervention'})
        assert 'Verified baseline' in result['text']
    else:
        with pytest.raises(StoreConflict,match='Novelty chưa đạt'):
            review_idea(runtime,{'title':'Intervention','text':'Measure intervention'})
    saved = json.loads((tmp_path/'automation/w/literature/0/review.json').read_text())
    assert saved['status'] == ('completed' if novel else 'rejected')
    assert saved['searches'][0]['papers'][0]['paperId']=='verified-paper'
    assert len(calls)==1 and calls[0][1]['timeout']==(5,20)


def test_literature_limits_http_retry_and_reuses_verified_cache(tmp_path,monkeypatch):
    calls = search_fixture(monkeypatch)
    search = LiteratureSearch(tmp_path)
    assert search('baseline')==[PAPER]
    assert search('baseline')==[PAPER]
    assert len(calls)==1
    calls.clear()
    def limited(*args,**kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=429,raise_for_status=lambda:(_ for _ in ()).throw(ValueError('rate limit')))
    monkeypatch.setattr('ai_scientist.workbench.research_literature.requests.get',limited)
    monkeypatch.setattr('ai_scientist.workbench.research_literature.time.sleep',lambda _:None)
    with pytest.raises(StoreConflict,match='429'):search('another query')
    assert len(calls)==3


def test_original_citation_round_selects_api_bibtex_and_stops(tmp_path,monkeypatch):
    calls = search_fixture(monkeypatch)
    answers = iter(['```json\n{"Query":"baseline","Description":"Prior baseline"}\n```',
                    '```json\n{"Selected":"[0]","Description":"Prior baseline"}\n```',
                    'No more citations needed'])
    (tmp_path/'idea.md').write_text('Test intervention',encoding='utf-8')
    research = tmp_path/'research';research.mkdir()
    owner = SimpleNamespace(root=tmp_path,stage_results={'draft':[{'metric':.8}]},check_running=lambda:None,
        service=SimpleNamespace(config=SimpleNamespace(codex_model='configured-agent-model'),store=SimpleNamespace(workspace=tmp_path)),
        query=lambda **kwargs:next(answers))
    pipeline = SimpleNamespace(root=research,owner=owner,plan=ResearchPlan(citations=True,citation_rounds=4),
                               client=CodexResearchClient(owner),seed_results={})
    assert 'research/references.bib' in gather_citations(pipeline)
    # Upstream normalizes the citation key, preserving the bibliographic fields.
    assert PAPER['citationStyles']['bibtex'].replace('Verified2025','verified2025') in (research/'references.bib').read_text()
    progress = json.loads((research/'citations_progress.json').read_text())
    assert progress['termination']=='model_finished' and len(progress['rounds'])==2
    assert len(calls)==1


def test_upstream_node_vlm_receives_actual_image_bytes_and_feedback(tmp_path):
    (tmp_path/'idea.md').write_text('Compare two curves',encoding='utf-8')
    path = tmp_path/'plot.png';Image.new('RGB',(80,80),'red').save(path)
    calls = []
    def query(**kwargs):
        content, images = detach_images(kwargs['user_message'],tmp_path/'attachments')
        calls.append(images)
        assert images[0].read_bytes()==path.read_bytes()
        assert not any(item.get('type')=='image_url' for item in content)
        return {'plot_analyses':[{'analysis':'The image is uniformly red; no measured curve is visible.'}],
                'valid_plots_received':False,'vlm_feedback_summary':'Replace the image with an actual metric plot.'}
    owner = SimpleNamespace(root=tmp_path,query=query,service=SimpleNamespace(config=SimpleNamespace(codex_model='preset-model')))
    node = SimpleNamespace(exp_dir=str(tmp_path),datasets_successfully_tested=['pinned'])
    analyze_plots(owner,node,[path])
    assert node.is_buggy_plots and node.vlm_feedback_summary.startswith('Replace')
    assert len(calls)==1 and node.datasets_successfully_tested==['pinned']
    saved = json.loads((tmp_path/'vlm-review.json').read_text())
    assert saved['valid_plots_received'] is False
    with pytest.raises(ValueError,match='chưa nhận'):analyze_plots(owner,node,[])


def test_upstream_pdf_review_and_selection_forward_images(tmp_path):
    import pymupdf
    plot = tmp_path/'plot.png';Image.new('RGB',(200,160),'blue').save(plot)
    root = tmp_path/'research';root.mkdir()
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((70,50),'Abstract')
        page.insert_text((70,70),'A measured comparison of methods.')
        page.insert_image(pymupdf.Rect(70,110,430,340),filename=str(plot))
        page.insert_text((70,360),'Figure 1: Measured comparison of two methods.')
        page.insert_text((70,395),'Figure 1 illustrates the comparison.')
        doc.save(root/'paper.pdf')
    attached = []
    def query(**kwargs):
        images = kwargs.get('image_paths',())
        assert images and all(p.is_file() for p in images)
        attached.append(images)
        message = json.dumps(kwargs['system_message'])
        if 'duplicates or variations' in message:return 'No duplicates found'
        return '```json\n{"assessment":"The blue image has no meaningful metric axes."}\n```'
    owner = SimpleNamespace(root=tmp_path,query=query,service=SimpleNamespace(config=SimpleNamespace(codex_model='antigravity-configured-model')))
    pipeline = SimpleNamespace(root=root,owner=owner,client=CodexResearchClient(owner))
    result = review_pdf(pipeline,selection=True,reflection=1)
    assert result['figures'] and result['selection'] and result['duplicates']=='No duplicates found'
    assert len(attached)>=3 and (root/'vlm-reflection-1.json').is_file()


def test_full_agent_grant_and_older_stage_bindings(repository):
    from tests.workbench.test_n8n_workflows import setup
    owner,project,_,spec,_=setup(repository)
    old = spec.model_dump()
    for stage in ('literature','citations','vision'):old['stages'].pop(stage)
    restored = WorkflowSpec.model_validate(old)
    assert restored.research.vlm is False and restored.stages['vision'].actor=='agent'
    full = WorkflowSpec.model_validate({**spec.model_dump(),'allow_agent_approval':True,'require_run_approval':False,
         'stages':{s:{**b.model_dump(),'actor':'agent'} for s,b in spec.stages.items()}})
    row=owner.create(project,uuid.uuid4().hex,full)
    assert row['spec']['allow_agent_approval'] and not row['spec']['require_run_approval']


def test_vlm_rejects_text_only_provider_before_kaggle_admission(repository,monkeypatch):
    from tests.workbench.test_n8n_workflows import setup
    owner,project,_,spec,_=setup(repository)
    spec=spec.model_copy(update={'research':ResearchPlan(vlm=True)},deep=True)
    spec.stages['vision'].harness='text-only'
    monkeypatch.setattr(owner.gateway.control_store,'harnesses',lambda:[SimpleNamespace(id='text-only',kind='cli_json')])
    with pytest.raises(StoreConflict,match='VLM cần preset'):
        owner.preflight(project,spec)
    assert owner.working.admissions==0


def test_native_codex_sends_image_inputs(tmp_path,monkeypatch):
    from ai_scientist.workbench.runtime import _agent_gateway_class
    gateway=_agent_gateway_class()
    package=gateway.__module__.rsplit('.',1)[0]
    harnesses=importlib.import_module(package+'.harnesses')
    models=importlib.import_module(package+'.models')
    import sys
    path=tmp_path/'plot.png';Image.new('RGB',(30,30),'red').save(path)
    captured=[]
    result={'summary':'{}','files':[],'checks':[],'handoff':''}
    raw='\n'.join(json.dumps(e) for e in [{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}},{'type':'turn.completed'}]).encode()
    monkeypatch.setattr(harnesses,'run_process',lambda args,workspace,body,**kw:(captured.append(args) or raw,{'tree_stopped':True}))
    adapter=harnesses.NativeHarness(models.HarnessSpec(id='vision',kind='native_codex',executable=sys.executable,enabled=True))
    handle=adapter.start(models.AgentSpec(id='vision',harness='vision'),tmp_path)
    adapter.send(handle,'Analyze attached image',request_id='r',timeout=30,emit=lambda _:None,started=lambda _:None,images=[path])
    assert '--image' in captured[0] and str(path.resolve()) in captured[0]


@pytest.mark.parametrize('supported',[True,False])
def test_acp_negotiates_real_image_blocks(tmp_path,supported):
    from tests.workbench.test_agent_team_execution import acp,models
    import sys
    image=tmp_path/'plot.png';Image.new('RGB',(30,30),'red').save(image)
    script=tmp_path/'fixture.py'
    script.write_text('''import json,sys,base64
for line in sys.stdin:
 m=json.loads(line);method=m['method'];p=m.get('params',{});result={}
 if method=='initialize':result={'protocolVersion':1,'agentCapabilities':{'promptCapabilities':{'image':SUPPORTED}}}
 elif method=='session/new':result={'sessionId':'vision'}
 elif method=='session/prompt':
  images=[b for b in p['prompt'] if b['type']=='image']
  assert len(images)==1 and base64.b64decode(images[0]['data']).startswith(b'\\x89PNG')
  print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'vision','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':json.dumps({'summary':'seen','files':[],'checks':[],'handoff':''})}}}}),flush=True)
  result={'stopReason':'end_turn'}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''.replace('SUPPORTED',str(supported)),encoding='utf-8')
    adapter=acp.AcpHarness(models.HarnessSpec(id='fixture',kind='acp',executable=sys.executable,args=[str(script)],protocol_version=1))
    handle=adapter.start(models.AgentSpec(id='vision'),tmp_path)
    if supported:
        result=adapter.send(handle,'Review image',request_id='v',timeout=5,emit=lambda _:None,started=lambda _:None,images=(image,))
        assert result.result.summary=='seen' and result.receipt['tree_stopped']
    else:
        with pytest.raises(ValueError,match='image prompt capability'):
            adapter.send(handle,'Review image',request_id='v',timeout=5,emit=lambda _:None,started=lambda _:None,images=(image,))


def test_semantic_scholar_key_survives_new_service_and_stays_out_of_evidence(tmp_path,monkeypatch):
    from ai_scientist.workbench.research_literature import saved_search_key,save_search_key
    calls=search_fixture(monkeypatch)
    save_search_key(tmp_path,'fixture-private-key')
    root=tmp_path/'evidence'
    LiteratureSearch(root,api_key=saved_search_key(tmp_path))('baseline')
    assert calls[0][1]['headers']['x-api-key']=='fixture-private-key'
    assert all('fixture-private-key' not in p.read_text() for p in root.glob('*.json'))
    assert saved_search_key(tmp_path)=='fixture-private-key'

