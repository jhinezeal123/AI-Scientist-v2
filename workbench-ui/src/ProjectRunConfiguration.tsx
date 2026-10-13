import {useEffect,useState} from 'react';
import {api,KaggleAccount} from './api';
import {configuration,ProjectConfiguration,RunConfiguration} from './projectConfiguration';
import RunExecutionFields from './RunExecutionFields';

export default function ProjectRunConfiguration({projectId,disabled,onSaved}:{projectId:string;disabled:boolean;onSaved:(saved:ProjectConfiguration)=>void}){
  const [saved,setSaved]=useState<ProjectConfiguration|null>(null),[draft,setDraft]=useState<RunConfiguration|null>(null);
  const [accounts,setAccounts]=useState<KaggleAccount[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  useEffect(()=>{let stopped=false;void Promise.allSettled([configuration(projectId),api<KaggleAccount[]>('/kaggle/accounts')]).then(([c,a])=>{
    if(stopped)return;
    if(c.status==='fulfilled'){setSaved(c.value);setDraft(c.value.run);}else setError(c.reason.message);
    if(a.status==='fulfilled')setAccounts(a.value);else setError(a.reason.message);
  });return()=>{stopped=true;};},[projectId]);
  async function save(){if(!saved||!draft)return;setBusy(true);setError('');try{
    const value=await api<ProjectConfiguration>(`/projects/${projectId}/configuration/run`,'PUT',{version:saved.version,run:draft});
    setSaved(value);setDraft(value.run);setNotice('Đã lưu môi trường mặc định cho run mới.');onSaved(value);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <details className="project-run-configuration"><summary>Môi trường mặc định · {saved?.run.account||'chọn riêng từng run'}</summary>
    <p className="muted">Hybrid dùng để điền sẵn, bạn vẫn cấu hình từng run trước khi chạy. Full agent dùng môi trường này trong phạm vi được cấp.</p>
    {error&&<p role="alert" className="alert error">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!draft?<p role="status">Đang đọc môi trường…</p>:<fieldset disabled={disabled||busy}>
      <RunExecutionFields value={draft} accounts={accounts} onChange={part=>{setDraft({...draft,...part});setNotice('');}}/>
      <button type="button" className="primary" disabled={JSON.stringify(draft)===JSON.stringify(saved?.run)} onClick={()=>void save()}>Lưu môi trường mặc định</button>
    </fieldset>}
  </details>;
}
