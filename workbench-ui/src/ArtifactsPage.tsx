import {useEffect,useState} from 'react';
import {api,Project,RunOutput} from './api';
import ArtifactLinks from './ArtifactLinks';

type SavedRun = {id:string;purpose:string;artifacts:string[];output?:RunOutput};

export default function ArtifactsPage({projectId,runId,outputOnly=false}:{projectId:string;runId:string;outputOnly?:boolean}) {
  const [project,setProject]=useState<Project|null>(null);
  const [run,setRun]=useState<SavedRun|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const valid=/^[0-9a-f]{32}$/.test(projectId) && /^[0-9a-f]{32}$/.test(runId);
  useEffect(()=>{
    document.title=`${outputOnly ? 'Output' : 'Artifacts'} · Run ${runId.slice(0,8)} · Workbench`;
    if (!valid){setError('Liên kết run không hợp lệ.');setLoading(false);return;}
    let cancelled=false;
    setLoading(true);setError('');setRun(null);
    Promise.all([api<Project[]>('/projects'),api<SavedRun>(`/projects/${projectId}/runs/${runId}`)])
      .then(([projects,run])=>{if (!cancelled){setProject(projects.find(project=>project.id===projectId) || null);setRun(run);}})
      .catch(error=>{if (!cancelled)setError(error instanceof Error ? error.message : String(error));})
      .finally(()=>{if (!cancelled)setLoading(false);});
    return ()=>{cancelled=true;};
  },[projectId,runId,valid,outputOnly]);
  const names=outputOnly ? run?.output?.files.map(file=>file.path) || [] : run?.artifacts || [];
  return <div className="artifacts-page"><main>
    <header><div><span className="eyebrow">{project?.name || 'WORKBENCH'} · Run {runId.slice(0,8)}</span>
      <h1>{outputOnly ? 'File Output' : 'Artifacts đã lưu'}</h1></div>
      <a href={valid ? `/?project=${projectId}&run=${runId}` : '/'}>← Về chi tiết run</a>
    </header>
    {loading && <p role="status" className="muted">Đang tải danh sách file…</p>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {run && <section className="panel" aria-label="Danh sách artifacts">
      <div className="panel-head"><h2>Run {run.id.slice(0,8)}</h2><span className="muted">{names.length} file</span></div>
      <p className="muted">{run.purpose}</p>
      {outputOnly && run.output && <>
        {run.output.directory && <code className="source-id">{run.output.directory}</code>}
        {run.output.status!=='completed' && <p className="alert">Đây là kết quả đã thu; công việc chưa được xác nhận hoàn tất.</p>}
      </>}
      {!names.length ? <p className="empty">{outputOnly ? 'Run chưa có file Output đã thu. Kết quả dạng nội dung nằm ở chi tiết run.' : 'Run chưa có artifact đã lưu.'}</p>
        : <ArtifactLinks projectId={projectId} runId={runId} names={names} previews={outputOnly}/>}
    </section>}
  </main></div>;
}
