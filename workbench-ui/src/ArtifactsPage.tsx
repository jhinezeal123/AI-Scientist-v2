import {useEffect,useState} from 'react';
import {api,Project} from './api';
import ArtifactLinks from './ArtifactLinks';

type SavedRun = {id:string;purpose:string;artifacts:string[]};

export default function ArtifactsPage({projectId,runId}:{projectId:string;runId:string}) {
  const [project,setProject]=useState<Project|null>(null);
  const [run,setRun]=useState<SavedRun|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const valid=/^[0-9a-f]{32}$/.test(projectId) && /^[0-9a-f]{32}$/.test(runId);
  useEffect(()=>{
    document.title=`Artifacts · Run ${runId.slice(0,8)} · Workbench`;
    if (!valid){setError('Liên kết run không hợp lệ.');setLoading(false);return;}
    let cancelled=false;
    setLoading(true);setError('');setRun(null);
    Promise.all([api<Project[]>('/projects'),api<SavedRun>(`/projects/${projectId}/runs/${runId}`)])
      .then(([projects,run])=>{if (!cancelled){setProject(projects.find(project=>project.id===projectId) || null);setRun(run);}})
      .catch(error=>{if (!cancelled)setError(error instanceof Error ? error.message : String(error));})
      .finally(()=>{if (!cancelled)setLoading(false);});
    return ()=>{cancelled=true;};
  },[projectId,runId,valid]);
  return <div className="artifacts-page"><main>
    <header><div><span className="eyebrow">{project?.name || 'WORKBENCH'} · Run {runId.slice(0,8)}</span>
      <h1>Artifacts đã lưu</h1></div>
      <a href={valid ? `/?project=${projectId}&run=${runId}` : '/'}>← Về chi tiết run</a>
    </header>
    {loading && <p role="status" className="muted">Đang tải danh sách file…</p>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {run && <section className="panel" aria-label="Danh sách artifacts">
      <div className="panel-head"><h2>Run {run.id.slice(0,8)}</h2><span className="muted">{run.artifacts.length} file</span></div>
      <p className="muted">{run.purpose}</p>
      {!run.artifacts.length ? <p className="empty">Run chưa có artifact đã lưu.</p>
        : <ArtifactLinks projectId={projectId} runId={runId} names={run.artifacts}/>}
    </section>}
  </main></div>;
}
