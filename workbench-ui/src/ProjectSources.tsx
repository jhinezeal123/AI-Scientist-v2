import {useEffect,useState} from 'react';
import {api,Resource} from './api';
import {configuration,ProjectConfiguration,IdeaSources} from './projectConfiguration';

export function ProjectSources({projectId,resources,onSaved}:{projectId:string;resources:Resource[];onSaved:()=>void}){
  const [saved,setSaved]=useState<ProjectConfiguration|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let stopped=false;configuration(projectId).then(value=>{if(!stopped)setSaved(value);}).catch(e=>{if(!stopped)setError(e.message);});return()=>{stopped=true;};},[projectId]);
  async function select(id:string,checked:boolean){if(!saved)return;setBusy(true);setError('');try{
    const resource_ids=checked?[...saved.resource_ids,id]:saved.resource_ids.filter(value=>value!==id);
    setSaved(await api<ProjectConfiguration>(`/projects/${projectId}/configuration/sources`,'PUT',{version:saved.version,resource_ids}));onSaved();
  }catch(e){setError(e instanceof Error?e.message:String(e));setSaved(await configuration(projectId));}finally{setBusy(false);}}
  return <details className="project-sources"><summary>Nguồn mặc định của project · {saved?.resource_ids.length||0} nguồn</summary>
    <p className="muted">Dùng khi agent sinh idea và làm nguồn mặc định cho idea mới. Thay đổi được lưu ngay; proposal đã duyệt giữ phiên bản nguồn đã ghim.</p>
    {resources.filter(r=>!r.deletion_pending).map(r=><label className="check" key={r.id}><input type="checkbox" disabled={busy||!saved}
      checked={saved?.resource_ids.includes(r.id)||false} onChange={e=>void select(r.id,e.target.checked)}/>{r.title} · v{r.version}</label>)}
    {!resources.length&&<p className="muted">Thêm nguồn vào Library để chọn.</p>}{error&&<p role="alert" className="alert error">{error}</p>}
  </details>;
}

export function IdeaSourceSelection({projectId,ideaId,resources,disabled,revision,onSelected,onReady}:{projectId:string;ideaId:string;resources:Resource[];disabled:boolean;revision:string;
  onSelected:(sources:string[])=>void;onReady:(ready:boolean)=>void}){
  const [saved,setSaved]=useState<IdeaSources|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let stopped=false;setSaved(null);onReady(false);if(!ideaId)return;
    api<IdeaSources>(`/projects/${projectId}/ideas/${ideaId}/sources`).then(value=>{if(!stopped){setSaved(value);onSelected(value.resource_ids);onReady(true);}})
      .catch(e=>{if(!stopped)setError(e.message);});return()=>{stopped=true;};},[projectId,ideaId,revision]);
  async function select(resource_ids:string[]|null){if(!saved)return;setBusy(true);onReady(false);setError('');try{
    const value=await api<IdeaSources>(`/projects/${projectId}/ideas/${ideaId}/sources`,'PUT',{version:saved.version,resource_ids});
    setSaved(value);onSelected(value.resource_ids);onReady(true);
  }catch(e){setError(e instanceof Error?e.message:String(e));const value=await api<IdeaSources>(`/projects/${projectId}/ideas/${ideaId}/sources`);setSaved(value);onSelected(value.resource_ids);onReady(true);}finally{setBusy(false);}}
  return <div className="stack"><p className="muted">{!saved?'Chọn một idea để xem nguồn.':saved.mode==='inherit'?'Đang kế thừa nguồn mặc định của project.':saved.mode==='pinned'?'Đang dùng nguồn đã ghim cho idea / proposal.':'Đang dùng nguồn riêng của idea.'} {saved&&'Nguồn đã chọn được lưu trên backend.'}</p>
    {saved&&saved.mode!=='inherit'&&<button type="button" disabled={disabled||busy} onClick={()=>void select(null)}>Dùng nguồn mặc định của project</button>}
    {resources.filter(r=>!r.deletion_pending).map(r=><label className="check" key={r.id}><input type="checkbox" disabled={disabled||busy||!saved}
      checked={saved?.resource_ids.includes(r.id)||false} onChange={e=>void select(e.target.checked?[...(saved?.resource_ids||[]),r.id]:(saved?.resource_ids||[]).filter(id=>id!==r.id))}/><span>{r.title}<small>v{r.version}</small></span></label>)}
    {error&&<p role="alert" className="alert error">{error}</p>}</div>;
}
