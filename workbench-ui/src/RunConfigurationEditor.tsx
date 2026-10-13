import {useEffect,useState} from 'react';
import {api,KaggleAccount} from './api';
import {RunConfiguration,RunExecutionConfiguration,sameExperimentStrategy} from './projectConfiguration';
import RunExecutionFields from './RunExecutionFields';

export default function RunConfigurationEditor({projectId,runId,disabled,canStart,onChanged,onReplanned}:{projectId:string;runId:string;
  disabled:boolean;canStart:boolean;onChanged:()=>void;onReplanned:(ideaId:string)=>void}){
  const [saved,setSaved]=useState<RunExecutionConfiguration|null>(null),[draft,setDraft]=useState<RunConfiguration|null>(null);
  const [accounts,setAccounts]=useState<KaggleAccount[]>([]),[remember,setRemember]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const base=`/projects/${projectId}/runs/${runId}`;
  useEffect(()=>{let stopped=false;void Promise.allSettled([api<RunExecutionConfiguration>(base+'/configuration'),api<KaggleAccount[]>('/kaggle/accounts')]).then(([c,a])=>{
    if(stopped)return;
    if(c.status==='fulfilled'){setSaved(c.value);setDraft(c.value.configuration);}else setError(c.reason.message);
    if(a.status==='fulfilled')setAccounts(a.value);else setError(a.reason.message);
  });return()=>{stopped=true;};},[projectId,runId]);
  async function perform(kind:'save'|'start'|'replan'){
    if(!saved||!draft)return;setBusy(true);setError('');setNotice('');try{
      if(kind==='replan'){
        const result=await api<{idea_id:string}>(base+'/replan','POST',{version:saved.version,configuration:draft});
        onReplanned(result.idea_id);onChanged();return;
      }
      const payload={version:saved.version,configuration:draft,remember_defaults:remember};
      if(kind==='save')await api(base+'/configuration','PUT',payload);else await api(base+'/start','POST',payload);
      const value=await api<RunExecutionConfiguration>(base+'/configuration');setSaved(value);setDraft(value.configuration);
      setNotice(kind==='save'?'Đã lưu cấu hình riêng của run.':'Đã duyệt cấu hình. Đang kiểm tra môi trường và bắt đầu run.');onChanged();
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  if(!saved||!draft)return <div className="context">{error?<p role="alert">{error}</p>:<p role="status">Đang đọc cấu hình run…</p>}</div>;
  const needsProposal=(saved.limits.execution_seconds!==null&&draft.execution_seconds>saved.limits.execution_seconds)
    ||(saved.limits.output_bytes!==null&&draft.output_bytes>saved.limits.output_bytes)
    ||!sameExperimentStrategy(draft.search,saved.planned_search)
    ||!!saved.execution_requirements?.accelerators.length&&!saved.execution_requirements.accelerators.includes(draft.accelerator);
  const valid=Number.isInteger(draft.ttl_seconds)&&draft.ttl_seconds>=180&&draft.ttl_seconds<=43200
    &&Number.isInteger(draft.execution_seconds)&&draft.execution_seconds>=1&&draft.execution_seconds<=draft.ttl_seconds-120
    &&Number.isInteger(draft.output_bytes)&&draft.output_bytes>=1&&draft.output_bytes<=10000000;
  return <section className="context stack run-configuration-editor" aria-label="Cấu hình và chạy">
    <div className="panel-head"><h3>Cấu hình và chạy</h3><span className="state-tag">{saved.approved?'Đã ghim':'Chưa chạy'}</span></div>
    <p className="muted">Loại công việc và benchmark theo Idea/Proposal đã duyệt. Môi trường dưới đây thuộc riêng run này.</p>
    {error&&<p className="alert error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {saved.approved?<><p>{draft.account} · {draft.accelerator} · {draft.ttl_seconds/60} phút</p>
      {canStart&&<button disabled={disabled||busy} onClick={()=>void perform('start')}>Tiếp tục với cấu hình đã duyệt</button>}</>:<fieldset disabled={disabled||busy}>
      <RunExecutionFields value={draft} accounts={accounts} allowSearch={saved.mode==='training_research'} onChange={part=>{setDraft({...draft,...part});setNotice('');}}/>
      {needsProposal&&<div className="alert"><p>Phần cứng, budget hoặc chiến lược thí nghiệm chưa phù hợp proposal được duyệt. Cần lập và duyệt proposal mới.</p>
        <button disabled={!valid} onClick={()=>void perform('replan')}>Lập lại proposal với cấu hình này</button></div>}
      <label className="check"><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/>Dùng cấu hình này làm mặc định cho run mới</label>
      {!canStart&&<p className="muted">Workflow chưa đến bước chạy. Bạn có thể lưu cấu hình trước.</p>}
      <div className="actions"><button disabled={!valid||!remember&&JSON.stringify(saved.configuration)===JSON.stringify(draft)} onClick={()=>void perform('save')}>Lưu cấu hình</button>
        <button className="primary" disabled={!canStart||!valid||!draft.account||needsProposal} onClick={()=>void perform('start')}>{busy?'Đang xử lý…':'Duyệt và chạy'}</button></div>
    </fieldset>}
  </section>;
}
