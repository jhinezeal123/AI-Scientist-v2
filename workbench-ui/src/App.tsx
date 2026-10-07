import {FormEvent, useEffect, useState} from 'react';
import {api, Context, History, Idea, ideaTitle, Project, Resource, Proposal} from './api';
import ProposalPanel from './ProposalPanel';
import RunPanel from './RunPanel';
import IdeaCards from './IdeaCards';

const blank = {kind: 'text' as Resource['kind'], title: '', url: '', content: ''};
const statusText = (status: string) => status === 'reference_only' ? 'Chỉ có liên kết · chưa đọc' : 'Có nội dung được cung cấp';

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(localStorage.getItem('workbench.project') || '');
  const [projectName, setProjectName] = useState('');
  const [tab, setTab] = useState('Library');
  const [resources, setResources] = useState<Resource[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [history, setHistory] = useState<History>({proposals: [], runs: []});
  const [proposals,setProposals] = useState<Proposal[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [ideaId, setIdeaId] = useState('');
  const [ideaText, setIdeaText] = useState('');
  const [title, setTitle] = useState('');
  const [editingIdea,setEditingIdea] = useState<Idea|null>(null);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState<Resource|null>(null);
  const [context, setContext] = useState<Context|null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    api<Project[]>('/projects').then(items => {
      setProjects(items);
      setProjectId(current => items.some(p => p.id === current) ? current : items[0]?.id || '');
    }).catch(e => setError(e.message));
  }, []);

  useEffect(() => {
    localStorage.setItem('workbench.project', projectId);
    setSelected([]); setContext(null); setIdeaId(''); setEditing(null); setForm(blank);
    setIdeaText(''); setTitle(''); setEditingIdea(null); setNotice(''); setResources([]); setIdeas([]); setProposals([]); setHistory({proposals: [], runs: []});
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([api<Resource[]>(`/projects/${projectId}/resources`),
      api<Idea[]>(`/projects/${projectId}/ideas?include_deleted=true`), api<History>(`/projects/${projectId}/history?include_deleted=true`),api<Proposal[]>(`/projects/${projectId}/proposals`)])
      .then(([r, i, h, p]) => {
        if (cancelled) return;
        setResources(r); setIdeas(i); setHistory(h); setProposals(p);
        setIdeaId(current => i.some(idea => idea.id === current && !idea.deleted_at) ? current : '');
      }).catch(e => {if (!cancelled) setError(e.message);})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [projectId, revision]);

  const planning = ideas.some(idea => idea.state === 'PLANNING');
  const implementing = history.runs.some(run => ['IMPLEMENTING','SUBMITTING','STARTING','WORKING','STOPPING'].includes(run.state));
  useEffect(() => {
    if (!planning && !implementing) return;
    const timer = window.setInterval(() => setRevision(n => n+1),1500);
    return () => window.clearInterval(timer);
  },[planning,implementing,projectId]);

  useEffect(() => {
    if (!projectId || !history.runs.length)return;
    let cancelled=false;let inFlight=false;
    const timer=window.setInterval(() => {
      if (inFlight)return;
      inFlight=true;
      api<History>(`/projects/${projectId}/history?include_deleted=true`).then(latest => {
        if (!cancelled)setHistory(old => JSON.stringify(old)===JSON.stringify(latest) ? old : latest);
      }).catch(() => { /* Run log polling shows read failures; retain the last history snapshot. */ })
        .finally(() => {inFlight=false;});
    },2000);
    return () => {cancelled=true;window.clearInterval(timer);};
  },[projectId,history.runs.length]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try {await work();} catch (e) {setError(e instanceof Error ? e.message : String(e));}
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
      await api(path, editing ? 'PUT' : 'POST', {...form, url: form.url || null,
        ...(editing ? {expected_version: editing.version} : {})});
      setForm(blank); setEditing(null); setContext(null); setRevision(n => n+1); setNotice('Đã lưu nguồn vào project.');
    });
  }

  const project = projects.find(p => p.id === projectId);
  function selectIdea(id:string) {
    setIdeaId(id);setContext(null);
  }
  return <div className="app">
    <aside className="rail">
      <div className="brand"><span className="brand-mark">∿</span><div>AI SCIENTIST<small>LOCAL WORKBENCH</small></div></div>
      <label>Project<select aria-label="Project đang mở" value={projectId} disabled={busy} onChange={e => setProjectId(e.target.value)}>
        {!projects.length && <option value="">Chưa có project</option>}
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      <form className="new-project" onSubmit={createProject}><label>Tên project mới<input value={projectName} required maxLength={120} onChange={e => setProjectName(e.target.value)}/></label>
        <button disabled={busy || !projectName.trim()}>Tạo project</button></form>
      <nav aria-label="Workbench">{['Library', 'Idea', 'Run'].map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{name}</button>)}</nav>
      <div className="rail-footer">Một project · nguồn riêng biệt<br/>Dữ liệu được lưu trên máy này.</div>
    </aside>
    <main>
      <header><div><span className="eyebrow">{project?.name || 'BẮT ĐẦU'}</span><h1>{tab === 'Library' ? 'Nguồn cho project' : tab === 'Idea' ? 'Ý tưởng triển khai' : 'Theo dõi lần chạy'}</h1></div>
        {project && <span className="mono project-id">{project.id.slice(0,8)}</span>}</header>
      {error && <div role="alert" className="alert error">{error}<button aria-label="Đóng lỗi" onClick={() => setError('')}>×</button></div>}
      {notice && <div role="status" className="alert">{notice}</div>}
      {!project ? <section className="panel welcome"><h2>Tạo project đầu tiên</h2><p>Lưu đề bài, nguồn dữ liệu và idea cùng một project. Bắt đầu bằng form bên trái.</p></section> : <>
        {loading && <p role="status" className="muted">Đang đọc project…</p>}
        {tab === 'Library' && <div className="columns">
          <section className="panel"><div className="panel-head"><h2>Library <span className="muted">{resources.length} nguồn</span></h2>
            <button disabled={busy || loading} onClick={() => void action(async () => {
              await api(`/projects/${projectId}/import-readiness`, 'POST'); setRevision(n => n+1); setNotice('Đã nhập nguồn competition đã đọc ở T01.');
            })}>Nhập nguồn T01</button></div>
            <p className="muted">Nguồn được lưu thành file riêng theo phiên bản. Agent nhận đường dẫn và tự tìm, đọc phần cần thiết.</p>
            <code className="source-id">.workbench/projects/{projectId}/library/</code>
            {!resources.length && <p className="empty">Chưa có nguồn. Thêm nguồn ở form bên cạnh hoặc nhập bản đọc T01.</p>}
            {resources.map(resource => <article className="resource" key={resource.id}>
              <div className="panel-head"><h3>{resource.title}</h3><button disabled={busy} onClick={() => {setEditing(resource); setForm({kind: resource.kind,title: resource.title,url: resource.url || '',content: resource.content});}}>Sửa nguồn</button></div>
              <p className="source-meta">{resource.kind} · v{resource.version} · {statusText(resource.status)}</p>
              <code className="source-id">{resource.id}</code>
              {resource.file_path && <div className="stack"><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}`} target="_blank" rel="noreferrer">Mở file nguồn ↗</a><code className="source-id">{resource.file_path}</code></div>}
              {resource.url && <a href={resource.url} target="_blank" rel="noreferrer">Mở nguồn ↗</a>}
              <details><summary>Xem nội dung và dấu kiểm tra</summary><pre>{resource.content || 'Chưa cung cấp nội dung nguồn. App chưa tải trang này.'}</pre><code className="source-id">SHA256 {resource.content_sha256}</code></details>
            </article>)}
          </section>
          <section className="panel"><h2>{editing ? `Sửa nguồn · v${editing.version}` : 'Thêm nguồn'}</h2>
            <form onSubmit={saveResource} className="stack"><label>Loại nguồn<select value={form.kind} onChange={e => setForm({...form,kind: e.target.value as Resource['kind']})}><option value="text">Text / đề bài</option><option value="url">URL</option><option value="dataset">Dataset reference</option></select></label>
              <label>Tiêu đề<input required maxLength={240} value={form.title} onChange={e => setForm({...form,title:e.target.value})}/></label>
              <label>URL nguồn<input type="url" value={form.url} maxLength={2000} onChange={e => setForm({...form,url:e.target.value})}/></label>
              <label>Nội dung / mô tả<textarea rows={10} maxLength={60000} value={form.content} onChange={e => setForm({...form,content:e.target.value})}/></label>
              <small className="muted">Chỉ lưu URL sẽ được đánh dấu “chưa đọc”. Nhập text không chứng minh app đã tải URL.</small>
              <div className="actions"><button className="primary" disabled={busy || loading}>Lưu nguồn</button>{editing && <button type="button" onClick={() => {setEditing(null);setForm(blank);}}>Hủy sửa</button>}</div>
            </form></section>
        </div>}
        {tab === 'Idea' && <div className="columns"><section className="panel"><h2>{editingIdea ? 'Sửa idea' : 'Idea mới'}</h2><p className="muted">Lưu bản nháp, chọn nguồn rồi lập proposal bằng Codex. Code và training chỉ thực hiện sau approval.</p>
          <form className="stack" onSubmit={event => {event.preventDefault(); void action(async () => {
            const path = `/projects/${projectId}/ideas` + (editingIdea ? `/${editingIdea.id}` : '');
            const idea = await api<Idea>(path, editingIdea ? 'PUT' : 'POST', {title,text: ideaText,...(editingIdea ? {expected_text:editingIdea.text,expected_title:editingIdea.title} : {})});
            setIdeaId(idea.id); setIdeaText(''); setTitle(''); setEditingIdea(null); setContext(null); setRevision(n => n+1); setNotice('Đã lưu idea.');
          });}}><label>Tiêu đề idea<input value={title} required maxLength={80} placeholder="Ví dụ: CNN nhỏ cho ảnh đất" onChange={e=>setTitle(e.target.value)}/></label>
          <label>Nội dung idea<textarea rows={8} required maxLength={20000} value={ideaText} onChange={e => setIdeaText(e.target.value)}/></label><div className="actions"><button className="primary" disabled={busy || loading || !title.trim() || !ideaText.trim()}>{editingIdea ? 'Lưu thay đổi idea' : 'Lưu idea'}</button>{editingIdea && <button type="button" onClick={() => {setEditingIdea(null);setIdeaText('');setTitle('');}}>Hủy sửa idea</button>}</div></form>
          <IdeaCards key={projectId} ideas={ideas} selectedId={ideaId} busy={busy} onSelect={selectIdea}
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
            {resources.map(resource => <label className="check" key={resource.id}><input type="checkbox" checked={selected.includes(resource.id)} onChange={e => {setSelected(current => e.target.checked ? [...current,resource.id] : current.filter(id => id !== resource.id));setContext(null);}}/><span>{resource.title}<small>v{resource.version} · {statusText(resource.status)}</small></span></label>)}
            <button disabled={busy || loading || !ideaId} onClick={() => void action(async () => {setContext(await api<Context>(`/projects/${projectId}/context`, 'POST', {idea_id:ideaId,resource_ids:selected}));})}>Xem context đã chọn</button>
            <button className="primary" disabled={busy || loading || planning || !ideaId || ideas.find(i => i.id === ideaId)?.state === 'APPROVED'} onClick={() => void action(async () => {
              await api(`/projects/${projectId}/plan`,'POST',{idea_id:ideaId,resource_ids:selected}); setRevision(n => n+1);setNotice('Đã gửi yêu cầu lập proposal cho Codex.');
            })}>Lập proposal bằng Codex</button>
          </div>{context && <div className="context"><h3>Context snapshot</h3><code className="source-id">SHA256 {context.context_sha256}</code>{context.snapshot.resources.map(resource => <div className="context-source" key={resource.id}><strong>{resource.title}</strong><small>v{resource.version} · {statusText(resource.status)}</small><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}`} target="_blank" rel="noreferrer">Mở file nguồn ↗</a><code className="source-id">{resource.file_path}</code></div>)}<details><summary>Xem context và đường dẫn nguồn</summary><pre>{JSON.stringify(context.snapshot,null,2)}</pre></details></div>}
        </section><ProposalPanel key={`${projectId}:${ideaId}`} idea={ideas.find(i => i.id === ideaId)} proposals={proposals} resources={resources} busy={busy || loading || planning} onAnswer={async (proposal,text) => {
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
        {tab === 'Run' && <RunPanel key={projectId} projectId={projectId} runs={history.runs} busy={busy || planning || implementing}
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
