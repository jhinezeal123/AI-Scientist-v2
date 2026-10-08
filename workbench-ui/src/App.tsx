import {FormEvent, useEffect, useRef, useState} from 'react';
import {api, ApiError, connectionFailure, Context, History, Idea, ideaTitle, Project, Resource, Proposal} from './api';
import ProposalPanel from './ProposalPanel';
import RunPanel from './RunPanel';
import IdeaCards from './IdeaCards';
import FileImport from './FileImport';
import SourceCards from './SourceCards';
import {statusText} from './sourceStatus';
import {loadProjectData} from './projectData';
import {lastProject, ProjectSession, readProjectSession, rememberProject, saveProjectSession} from './projectSession';

const blank = {title: '', content: ''};
const initialPage=new URLSearchParams(window.location.search);

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(initialPage.get('project') || lastProject());
  const [projectName, setProjectName] = useState('');
  const [tab, setTab] = useState<ProjectSession['tab']>(()=>initialPage.has('run') ? 'Run' : readProjectSession(projectId).tab);
  const [resources, setResources] = useState<Resource[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [history, setHistory] = useState<History>({proposals: [], runs: []});
  const [proposals,setProposals] = useState<Proposal[]>([]);
  const [selected, setSelected] = useState<string[]>(()=>readProjectSession(projectId).sourceIds);
  const [ideaId, setIdeaId] = useState(()=>readProjectSession(projectId).ideaId);
  const [runId,setRunId] = useState(()=>initialPage.get('run') || readProjectSession(projectId).runId);
  const [sessionProject,setSessionProject] = useState(projectId);
  const firstRestore=useRef(true);
  const [ideaText, setIdeaText] = useState('');
  const [title, setTitle] = useState('');
  const [editingIdea,setEditingIdea] = useState<Idea|null>(null);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState<Resource|null>(null);
  const [replacing,setReplacing] = useState<Resource|null>(null);
  const [context, setContext] = useState<Context|null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const [connectionRevision,setConnectionRevision] = useState(0);
  const [connectionError,setConnectionError] = useState('');
  const [reviewedVariantSources,setReviewedVariantSources] = useState('');
  const refresh=()=>setConnectionRevision(n=>n+1);

  useEffect(() => {
    let cancelled=false;
    api<Project[]>('/projects').then(items => {
      if (cancelled)return;
      setProjects(items);
      setProjectId(current => items.some(p => p.id === current) ? current : items[0]?.id || '');
      if (!items.length)setConnectionError('');
    }).catch(e => {if (!cancelled)setConnectionError(connectionFailure(e)
      ? 'Mất kết nối backend. Đang chờ kết nối lại để đọc dữ liệu đã lưu.' : e.message);});
    return ()=>{cancelled=true;};
  }, [connectionRevision]);

  useEffect(() => {
    rememberProject(projectId);
    const saved=readProjectSession(projectId);
    if (firstRestore.current && initialPage.has('run')) {
      saved.tab='Run';saved.runId=initialPage.get('run') || '';
    }
    firstRestore.current=false;
    setTab(saved.tab);setRunId(saved.runId);setSelected(saved.sourceIds);setIdeaId(saved.ideaId);setSessionProject(projectId);
    setContext(null);setEditing(null);setForm(blank);setReplacing(null);
    setIdeaText(''); setTitle(''); setEditingIdea(null); setNotice(''); setResources([]); setIdeas([]); setProposals([]); setHistory({proposals: [], runs: []});
    setError('');
  }, [projectId]);

  useEffect(()=>{
    if (sessionProject!==projectId || !projectId)return;
    saveProjectSession(projectId,{tab,ideaId,sourceIds:selected,runId});
    const url=new URL(window.location.href);
    url.searchParams.set('project',projectId);
    if (tab==='Run' && runId)url.searchParams.set('run',runId);
    else url.searchParams.delete('run');
    if (url.href!==window.location.href)window.history.replaceState(null,'',url);
  },[sessionProject,projectId,tab,ideaId,selected,runId]);

  useEffect(()=>{
    if (!connectionError)return;
    const timer=window.setTimeout(refresh,4000);
    return ()=>window.clearTimeout(timer);
  },[connectionError,connectionRevision]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    loadProjectData(projectId)
      .then(([r, i, h, p]) => {
        if (cancelled) return;
        setResources(r); setIdeas(i); setHistory(h); setProposals(p);
        setConnectionError('');
        setSelected(current=>current.filter(id=>r.some(source=>source.id===id && !source.deletion_pending)));
        setIdeaId(current => i.some(idea => idea.id === current && !idea.deleted_at) ? current : '');
        setRunId(current=>h.runs.some(run=>run.id===current && !run.deleted_at) ? current : '');
      }).catch(e => {if (!cancelled)setConnectionError(connectionFailure(e)
        ? 'Mất kết nối backend. Đang chờ kết nối lại để đọc dữ liệu đã lưu.' : e.message);})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [projectId, revision, connectionRevision]);

  const planning = ideas.some(idea => idea.state === 'PLANNING');
  const implementing = history.runs.some(run => ['IMPLEMENTING','SUBMITTING','STARTING','WORKING','STOPPING'].includes(run.state));
  useEffect(() => {
    if ((!planning && !implementing) || connectionError) return;
    const timer = window.setInterval(() => setRevision(n => n+1),1500);
    return () => window.clearInterval(timer);
  },[planning,implementing,projectId,connectionError]);

  useEffect(() => {
    if (!projectId || !history.runs.length || connectionError)return;
    let cancelled=false;let inFlight=false;
    const timer=window.setInterval(() => {
      if (inFlight)return;
      inFlight=true;
      api<History>(`/projects/${projectId}/history?include_deleted=true`).then(latest => {
        if (!cancelled)setHistory(old => JSON.stringify(old)===JSON.stringify(latest) ? old : latest);
      }).catch(e => {if (!cancelled && connectionFailure(e))setConnectionError('Mất kết nối backend. Đang chờ kết nối lại để đọc dữ liệu đã lưu.');})
        .finally(() => {inFlight=false;});
    },2000);
    return () => {cancelled=true;window.clearInterval(timer);};
  },[projectId,history.runs.length,connectionError]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try {await work();} catch (e) {
      const disconnected=connectionFailure(e) && !(e instanceof ApiError);
      setError(disconnected ? 'Chưa nhận được phản hồi. Tải lại dữ liệu để kiểm tra trạng thái trước khi yêu cầu lại thao tác.'
        : e instanceof Error ? e.message : String(e));
      if (disconnected)setConnectionError('Mất kết nối backend. Đang chờ kết nối lại để đọc dữ liệu đã lưu.');
    }
    finally {setBusy(false);}
  }

  function createProject(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      const project = await api<Project>('/projects', 'POST', {name: projectName});
      setProjects(await api<Project[]>('/projects')); setProjectId(project.id); setProjectName('');
    });
  }

  function saveResource(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      const path = `/projects/${projectId}/resources` + (editing ? `/${editing.id}` : '');
      await api(path, editing ? 'PUT' : 'POST', {...form,
        ...(editing ? {expected_version: editing.version} : {})});
      setForm(blank); setEditing(null); setContext(null); setRevision(n => n+1); setNotice('Đã lưu nguồn vào project.');
    });
  }

  const project = projects.find(p => p.id === projectId);
  const unavailable=loading || !!connectionError;
  const selectedIdea=ideas.find(idea=>idea.id===ideaId);
  const parentSources=selectedIdea?.variant?.baseline.parent.sources || [];
  const changedParentSources=parentSources.filter(parent=>{
    const current=resources.find(source=>source.id===parent.id && !source.deletion_pending);
    return !current || current.version!==parent.version || current.content_sha256!==parent.content_sha256;
  });
  const variantSourceReviewRequired=changedParentSources.length>0 && reviewedVariantSources!==ideaId;
  const sourceVersionSignature=JSON.stringify(resources.filter(source=>!source.deletion_pending)
    .map(source=>[source.id,source.version,source.content_sha256]));
  useEffect(()=>{setReviewedVariantSources('');},[projectId,sourceVersionSignature]);
  function selectIdea(id:string) {
    setIdeaId(id);setContext(null);
    setReviewedVariantSources('');
    const nextIdea=ideas.find(idea=>idea.id===id);
    const oldSources=nextIdea?.variant?.baseline.parent.sources || [];
    const needsReview=oldSources.some(parent=>{
      const current=resources.find(source=>source.id===parent.id && !source.deletion_pending);
      return !current || current.version!==parent.version || current.content_sha256!==parent.content_sha256;
    });
    if (!needsReview && nextIdea?.variant)setReviewedVariantSources(id);
    const latest=proposals.filter(proposal=>proposal.idea_id===id).sort((a,b)=>b.version-a.version)[0];
    if (latest)setSelected(latest.context_snapshot.resources.map(source=>source.id)
      .filter(sourceId=>resources.some(source=>source.id===sourceId && !source.deletion_pending)));
  }
  async function createVariant(id:string,requestId:string,variantTitle:string,purpose:string,changeSummary:string):Promise<Idea|undefined> {
    let created:Idea|undefined;
    await action(async()=>{
      created=await api<Idea>(`/projects/${projectId}/runs/${id}/variants`,'POST',{
        request_id:requestId,title:variantTitle,purpose,change_summary:changeSummary,
      });
      const sources=created.variant?.baseline.parent.sources || [];
      setSelected(sources.map(source=>source.id).filter(sourceId=>resources.some(source=>source.id===sourceId && !source.deletion_pending)));
      const hasChanged=sources.some(parent=>{
        const current=resources.find(source=>source.id===parent.id && !source.deletion_pending);
        return !current || current.version!==parent.version || current.content_sha256!==parent.content_sha256;
      });
      setReviewedVariantSources(hasChanged ? '' : created.id);
      setIdeaId(created.id);setEditingIdea(null);setIdeaText('');setTitle('');setContext(null);setTab('Idea');
      setRevision(n=>n+1);setNotice('Đã lưu idea biến thể ở trạng thái bản nháp. Chưa gọi planner hoặc tạo run.');
    });
    return created;
  }
  function openRun(id:string) {setTab('Run');setRunId(id);}
  return <div className="app">
    <aside className="rail">
      <div className="brand"><span className="brand-mark">∿</span><div>AI SCIENTIST<small>LOCAL WORKBENCH</small></div></div>
      <label>Project<select aria-label="Project đang mở" value={projectId} disabled={busy} onChange={e => setProjectId(e.target.value)}>
        {!projects.length && <option value="">Chưa có project</option>}
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      <form className="new-project" onSubmit={createProject}><label>Tên project mới<input value={projectName} required maxLength={120} onChange={e => setProjectName(e.target.value)}/></label>
        <button disabled={busy || unavailable || !projectName.trim()}>Tạo project</button></form>
      <nav aria-label="Workbench">{(['Library', 'Idea', 'Run'] as const).map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{name}</button>)}</nav>
      <div className="rail-footer">Một project · nguồn riêng biệt<br/>Dữ liệu được lưu trên máy này.</div>
    </aside>
    <main>
      <header><div><span className="eyebrow">{project?.name || 'BẮT ĐẦU'}</span><h1>{tab === 'Library' ? 'Nguồn cho project' : tab === 'Idea' ? 'Ý tưởng triển khai' : 'Theo dõi lần chạy'}</h1></div>
        {project && <span className="mono project-id">{project.id.slice(0,8)}</span>}</header>
      {error && <div role="alert" className="alert error">{error}<button aria-label="Đóng lỗi" onClick={() => setError('')}>×</button></div>}
      {notice && <div role="status" className="alert">{notice}</div>}
      {connectionError && <div role="alert" className="alert error connection-notice"><span>{connectionError} Kết nối lại chỉ đọc trạng thái; bạn quyết định lượt chạy tiếp theo.</span>
        <button type="button" onClick={refresh}>Kết nối lại</button></div>}
      {!project ? <section className="panel welcome"><h2>Tạo project đầu tiên</h2><p>Lưu đề bài, nguồn dữ liệu và idea cùng một project. Bắt đầu bằng form bên trái.</p></section> : <>
        {loading && <p role="status" className="muted">Đang đọc project…</p>}
        {tab === 'Library' && <div className="columns">
          <section className="panel"><div className="panel-head"><h2>Library <span className="muted">{resources.length} nguồn</span></h2></div>
            <p className="muted">Nguồn được lưu thành file riêng theo phiên bản. Agent nhận đường dẫn và tự tìm, đọc phần cần thiết.</p>
            <code className="source-id">{project.library_path}</code>
            <SourceCards key={projectId} projectId={projectId} resources={resources} busy={busy || unavailable}
              deletionBlocked={planning || implementing} onEdit={resource=>{
                if (resource.attachment){setReplacing(resource);return;}
                setEditing(resource); setForm({title: resource.title,content: resource.url && !resource.content.includes(resource.url)
                  ? `${resource.url}\n\n${resource.content}` : resource.content});
              }} onDelete={async resource=>{await action(async()=>{
                try {
                  const result=await api<{removed_files:number;freed_bytes:number}>(`/projects/${projectId}/resources/${resource.id}`,'DELETE');
                  setSelected(current=>current.filter(id=>id!==resource.id));setContext(null);
                  if (editing?.id===resource.id){setEditing(null);setForm(blank);}
                  if (replacing?.id===resource.id)setReplacing(null);
                  const bytes=result.freed_bytes;
                  const size=bytes>=1_048_576 ? `${(bytes/1_048_576).toFixed(1)} MB` : bytes>=1024 ? `${(bytes/1024).toFixed(1)} KB` : `${bytes} byte`;
                  setNotice(`Đã xóa vĩnh viễn nguồn và ${result.removed_files} file (${size}).`);
                } finally {setContext(null);setRevision(n=>n+1);}
              });}}/>
          </section>
          <section className="panel"><h2>{editing ? `Sửa nguồn · v${editing.version}` : 'Thêm nguồn'}</h2>
            <form onSubmit={saveResource} className="stack">
              <label>Tiêu đề<input required maxLength={240} value={form.title} onChange={e => setForm({...form,title:e.target.value})}/></label>
              <label>Nội dung / mô tả<textarea rows={10} maxLength={60000} value={form.content} placeholder="Nhập nội dung, mô tả hoặc URL nguồn" onChange={e => setForm({...form,content:e.target.value})}/></label>
              <small className="muted">Có thể dán một hoặc nhiều URL tại đây. Chỉ lưu URL sẽ được đánh dấu “chưa đọc”; app chưa tải nội dung trang.</small>
              <div className="actions"><button className="primary" disabled={busy || unavailable}>Lưu nguồn</button>{editing && <button type="button" onClick={() => {setEditing(null);setForm(blank);}}>Hủy sửa</button>}</div>
            </form><FileImport key={`${projectId}:${replacing?.id || 'new'}`} projectId={projectId} busy={busy || unavailable} replacing={replacing}
              onCancel={()=>setReplacing(null)} onUpload={action} onSaved={source=>{setReplacing(null);setContext(null);setRevision(n=>n+1);
                setNotice(`Đã nhập ${source.title} · v${source.version}: ${statusText(source.status)}.`);}}/></section>
        </div>}
        {tab === 'Idea' && <div className="columns"><section className="panel"><h2>{editingIdea ? 'Sửa idea' : 'Idea mới'}</h2><p className="muted">Lưu bản nháp, chọn nguồn rồi lập proposal bằng Codex. Code và training chỉ thực hiện sau approval.</p>
          <form className="stack" onSubmit={event => {event.preventDefault(); void action(async () => {
            const path = `/projects/${projectId}/ideas` + (editingIdea ? `/${editingIdea.id}` : '');
            const idea = await api<Idea>(path, editingIdea ? 'PUT' : 'POST', {title,text: ideaText,...(editingIdea ? {expected_text:editingIdea.text,expected_title:editingIdea.title} : {})});
            setIdeaId(idea.id); setIdeaText(''); setTitle(''); setEditingIdea(null); setContext(null); setRevision(n => n+1); setNotice('Đã lưu idea.');
          });}}><label>Tiêu đề idea<input value={title} required maxLength={80} placeholder="Ví dụ: CNN nhỏ cho ảnh đất" onChange={e=>setTitle(e.target.value)}/></label>
          <label>Nội dung idea<textarea rows={8} required maxLength={20000} value={ideaText} onChange={e => setIdeaText(e.target.value)}/></label><div className="actions"><button className="primary" disabled={busy || unavailable || !title.trim() || !ideaText.trim()}>{editingIdea ? 'Lưu thay đổi idea' : 'Lưu idea'}</button>{editingIdea && <button type="button" onClick={() => {setEditingIdea(null);setIdeaText('');setTitle('');}}>Hủy sửa idea</button>}</div></form>
          <IdeaCards key={projectId} ideas={ideas} selectedId={ideaId} busy={busy || unavailable} onSelect={selectIdea}
            onDelete={async id=>{await action(async()=>{
              await api(`/projects/${projectId}/ideas/${id}`,'DELETE');setIdeaId('');setContext(null);setEditingIdea(null);setIdeaText('');setTitle('');
              setRevision(n=>n+1);setNotice('Đã xóa idea khỏi danh sách. Có thể khôi phục trong mục Đã xóa.');
            });}}
            onRestore={async id=>{await action(async()=>{
              await api(`/projects/${projectId}/ideas/${id}/restore`,'POST');setRevision(n=>n+1);setNotice('Đã khôi phục idea.');
            });}}
            onEdit={idea=>{setEditingIdea(idea);setIdeaText(idea.text);setTitle(idea.title);}}
            onRename={async (idea,newTitle)=>{await action(async()=>{
              await api(`/projects/${projectId}/ideas/${idea.id}/title`,'PATCH',{title:newTitle,expected_title:idea.title});
              setRevision(n=>n+1);setNotice('Đã lưu tiêu đề idea.');
            });}}/>
        </section><section className="panel"><h2>Nguồn sẽ đưa cho agent</h2><p className="muted">Chọn nguồn để đưa đường dẫn file vào context. Agent tự tìm và đọc phần cần thiết; xem trước không gọi Codex.</p>
          <div className="stack"><label>Idea đã lưu<select value={ideaId} onChange={e => selectIdea(e.target.value)}><option value="">Chọn idea</option>{ideas.filter(idea=>!idea.deleted_at).map(idea => <option key={idea.id} value={idea.id}>{ideaTitle(idea)}</option>)}</select></label>
            {variantSourceReviewRequired && <div role="alert" className="alert error">
              <p>Nguồn từ run cha đã đổi hoặc bị xóa. Đã chọn các nguồn còn tồn tại; proposal sẽ ghim phiên bản hiện hành. Kiểm tra danh sách nguồn trước khi tiếp tục.</p>
              <ul>{changedParentSources.map(source=>{
                const current=resources.find(item=>item.id===source.id && !item.deletion_pending);
                return <li key={source.id}>{source.title}: {current ? `cha v${source.version}, hiện tại v${current.version}` : 'đã bị xóa; không tự khôi phục'}.</li>;
              })}</ul>
              <label className="check"><input type="checkbox" checked={reviewedVariantSources===ideaId}
                onChange={event=>setReviewedVariantSources(event.target.checked ? ideaId : '')}/>
                <span>Tôi đã kiểm tra nguồn đang chọn cho proposal mới.</span></label>
            </div>}
            {resources.filter(resource=>!resource.deletion_pending).map(resource => <label className="check" key={resource.id}><input type="checkbox" checked={selected.includes(resource.id)} onChange={e => {setSelected(current => e.target.checked ? [...current,resource.id] : current.filter(id => id !== resource.id));setContext(null);setReviewedVariantSources('');}}/><span>{resource.title}<small>v{resource.version} · {statusText(resource.status)}</small></span></label>)}
            <button disabled={busy || unavailable || !ideaId} onClick={() => void action(async () => {setContext(await api<Context>(`/projects/${projectId}/context`, 'POST', {idea_id:ideaId,resource_ids:selected}));})}>Xem context đã chọn</button>
            <button className="primary" disabled={busy || unavailable || planning || variantSourceReviewRequired || !ideaId || ideas.find(i => i.id === ideaId)?.state === 'APPROVED'} onClick={() => void action(async () => {
              await api(`/projects/${projectId}/plan`,'POST',{idea_id:ideaId,resource_ids:selected}); setRevision(n => n+1);setNotice('Đã gửi yêu cầu lập proposal cho Codex.');
            })}>Lập proposal bằng Codex</button>
          </div>{context && <div className="context"><h3>Context snapshot</h3><code className="source-id">SHA256 {context.context_sha256}</code>{context.snapshot.resources.map(resource => <div className="context-source" key={resource.id}><strong>{resource.title}</strong><small>v{resource.version} · {statusText(resource.status)}</small><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}`} target="_blank" rel="noreferrer">Mở file nguồn ↗</a><code className="source-id">{resource.file_path}</code></div>)}<details><summary>Xem context và đường dẫn nguồn</summary><pre>{JSON.stringify(context.snapshot,null,2)}</pre></details></div>}
        </section><ProposalPanel key={`${projectId}:${ideaId}`} idea={selectedIdea} proposals={proposals} resources={resources} busy={busy || unavailable || planning || variantSourceReviewRequired}
          onOpenParent={openRun}
          onReplan={async()=>{await action(async()=>{
            await api(`/projects/${projectId}/plan`,'POST',{idea_id:ideaId,resource_ids:selected});
            setRevision(n=>n+1);setNotice('Đã yêu cầu Codex tiếp tục từ trao đổi đã lưu và các nguồn đang chọn.');
          });}} onAnswer={async (proposal,text) => {
          let saved = false;
          await action(async () => {await api(`/projects/${projectId}/ideas/${ideaId}/answer`,'POST',{proposal_id:proposal.id,version:proposal.version,text});setRevision(n => n+1);setNotice(`Đã lưu câu trả lời. Bấm “Tiếp tục lập proposal v${proposal.version + 1}” để Codex tiếp tục.`);saved = true;});
          if (!saved) throw new Error('Answer not saved');
        }} onContinue={async proposal => {await action(async () => {
          const resourceIds = proposal.context_snapshot.resources.map(source => source.id);
          await api(`/projects/${projectId}/plan`,'POST',{idea_id:proposal.idea_id,resource_ids:resourceIds});
          setSelected(resourceIds);setContext(null);setRevision(n => n+1);
          setNotice(`Đã gửi câu trả lời và nguồn của v${proposal.version} cho Codex để lập proposal v${proposal.version + 1}.`);
        });}} onApprove={async proposal => {await action(async () => {
          const run = await api<{id:string}>(`/projects/${projectId}/proposals/${proposal.id}/approve`,'POST',{version:proposal.version,context_sha256:proposal.context_sha256});setRevision(n => n+1);setNotice(`Đã duyệt và tạo run ${run.id}. Chưa chạy code/training.`);
        });}}/></div>}
        {tab === 'Run' && <RunPanel key={projectId} projectId={projectId} selectedRunId={runId} onSelect={setRunId} runs={history.runs} busy={busy || unavailable || planning || implementing}
          onCreateVariant={createVariant}
          onDelete={async id=>{await action(async()=>{
            await api(`/projects/${projectId}/runs/${id}`,'DELETE');setRevision(n=>n+1);setNotice('Đã xóa run khỏi danh sách. Artifacts được giữ để khôi phục.');
          });}}
          onRestore={async id=>{await action(async()=>{
            await api(`/projects/${projectId}/runs/${id}/restore`,'POST');setRevision(n=>n+1);setNotice('Đã khôi phục run.');
          });}}
          onWorking={async (id,accelerator,ttl) => {
          await action(async () => {await api(`/projects/${projectId}/runs/${id}/working`, 'POST',{accelerator,ttl_seconds:ttl});setRevision(n => n+1);setNotice('Đã bắt đầu Working: mở Kaggle, viết và chạy code, thu kết quả rồi dừng phiên.');});
        }} onStop={async id => {
          await action(async () => {await api(`/projects/${projectId}/runs/${id}/stop`, 'POST');setRevision(n => n+1);setNotice('Đã yêu cầu dừng Working. Backend sẽ xác nhận phiên Kaggle đã dừng.');});
        }} onReconcile={async id => {
          await action(async () => {await api(`/projects/${projectId}/runs/${id}/reconcile`, 'POST');setRevision(n => n+1);setNotice('Đã đối soát trạng thái qua MCP; không gửi notebook lần nữa.');});
        }} onRetry={async id => {
          let newId:string|undefined;
          await action(async () => {
            const run = await api<{id:string}>(`/projects/${projectId}/runs/${id}/retry`, 'POST',
              {request_id:crypto.randomUUID().replaceAll('-','')});
            newId=run.id;setRevision(n => n+1);
            setNotice(`Đã tạo run ${run.id.slice(0,8)} từ proposal đã duyệt. Bấm Working khi sẵn sàng.`);
          });
          return newId;
        }}/>} 
      </>}
    </main>
  </div>;
}
