import {useEffect,useState} from 'react';
import {api,Benchmark,KaggleAccount} from './api';
import {configuration,ProjectConfiguration,RunConfiguration} from './projectConfiguration';
import RunSetupFields from './RunSetupFields';
import ExperimentSettings from './ExperimentSettings';
import ResearchOptions from './ResearchOptions';

/** Run owns execution defaults. Workflow consumes the saved version only. */
export default function ProjectRunConfiguration({projectId,disabled,onSaved}:{projectId:string;disabled:boolean;onSaved:(saved:ProjectConfiguration)=>void}){
  const [saved,setSaved]=useState<ProjectConfiguration|null>(null),[draft,setDraft]=useState<RunConfiguration|null>(null);
  const [benchmarks,setBenchmarks]=useState<Benchmark[]>([]),[accounts,setAccounts]=useState<KaggleAccount[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  useEffect(()=>{let stopped=false;setError('');void Promise.allSettled([configuration(projectId),api<Benchmark[]>(`/projects/${projectId}/benchmarks`),api<KaggleAccount[]>('/kaggle/accounts')]).then(([c,b,a])=>{
    if(stopped)return;
    if(c.status==='fulfilled'){setSaved(c.value);setDraft(c.value.run);}else setError(c.reason.message);
    if(b.status==='fulfilled')setBenchmarks(b.value);else setError(b.reason.message);
    if(a.status==='fulfilled')setAccounts(a.value);else setError(a.reason.message);
  });return()=>{stopped=true;};},[projectId]);
  const dirty=!!draft&&!!saved&&JSON.stringify(draft)!==JSON.stringify(saved.run);
  function set(value:Partial<RunConfiguration>){setDraft(old=>old?{...old,...value}:old);setNotice('');}
  async function save(){if(!saved||!draft)return;setBusy(true);setError('');try{
    const value=await api<ProjectConfiguration>(`/projects/${projectId}/configuration/run`,'PUT',{version:saved.version,run:draft});
    setSaved(value);setDraft(value.run);setNotice('Đã lưu cấu hình Run. Áp dụng cho công việc mới; các lần đã duyệt giữ cấu hình đã ghim.');onSaved(value);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function reload(){setBusy(true);try{const value=await configuration(projectId);setSaved(value);setDraft(value.run);setError('');setNotice('');}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <details className="project-run-configuration" open={!saved?.workflow}><summary>Cấu hình Run mặc định của project</summary>
    <p className="muted">Loại công việc, benchmark, môi trường và đầu ra được thiết lập tại đây. Idea mới kế thừa; workflow dùng cấu hình đã lưu khi tạo lượt nghiên cứu.</p>
    {error&&<div role="alert" className="alert error"><p>{error}</p><button type="button" disabled={busy} onClick={()=>void reload()}>Tải lại cấu hình</button></div>}
    {notice&&<p role="status" className="alert">{notice}</p>}
    {!draft?<p role="status">Đang đọc cấu hình Run…</p>:<fieldset disabled={disabled||busy}>
      <RunSetupFields spec={draft} options={{benchmarks,accounts}} onChange={set}/>
      <div className="team-create"><label>Phần cứng<select value={draft.accelerator} onChange={e=>set({accelerator:e.target.value})}>{[['cpu','CPU'],['NvidiaT4','GPU · T4 x2'],['TpuV5E8','TPU · v5e-8'],['TpuV6E8','TPU · v6e-8']].map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
        <label>Thời hạn phiên (giây)<input type="number" min={180} max={43200} value={draft.ttl_seconds} onChange={e=>set({ttl_seconds:Number(e.target.value)})}/></label>
        <label>Budget thực thi (giây)<input type="number" min={60} max={43080} value={draft.execution_seconds} onChange={e=>set({execution_seconds:Number(e.target.value)})}/></label>
        <label>Output tối đa (bytes)<input type="number" min={1} max={10000000} value={draft.output_bytes} onChange={e=>set({output_bytes:Number(e.target.value)})}/></label></div>
      <p className="muted">Chừa ít nhất 120 giây cuối phiên để thu kết quả.</p>
      {draft.mode==='training_research'&&<><ExperimentSettings spec={draft} onChange={set}/>
        <ResearchOptions value={draft.research} onChange={research=>set({research})}/>
        <details><summary>Literature và đánh giá khoa học</summary><label className="check"><input type="checkbox" checked={draft.research.literature} onChange={e=>set({research:{...draft.research,literature:e.target.checked}})}/>Literature / novelty trước proposal</label>
          {draft.research.literature&&<label>Số vòng tìm tài liệu và phản biện tối đa<input type="number" min={2} max={20} value={draft.research.literature_rounds} onChange={e=>set({research:{...draft.research,literature_rounds:Number(e.target.value)}})}/></label>}
          <label>Số vòng sửa figures / bài<input type="number" min={0} max={10} value={draft.research.reflections} onChange={e=>set({research:{...draft.research,reflections:Number(e.target.value)}})}/></label>
          <p className="muted">Citation và VLM dùng đầu ra đã chọn ở trên. VLM cần preset nhận ảnh; chọn preset tại Workflow.</p>
        </details></>}
      {dirty&&<p className="muted">Có thay đổi chưa lưu. Workflow dùng bản đã lưu.</p>}
      <button type="button" className="primary" disabled={!dirty} onClick={()=>void save()}>Lưu cấu hình Run</button>
    </fieldset>}
  </details>;
}
