import {useEffect,useState} from 'react';
import {api,History,Project} from './api';
import ProjectRunTree from './ProjectRunTree';

export default function ProjectTreePage({projectId}:{projectId:string}) {
  const [runs,setRuns]=useState<History['runs']>([]),[name,setName]=useState(''),[error,setError]=useState('');
  useEffect(()=>{
    let closed=false;
    const load=()=>Promise.all([api<History>(`/projects/${projectId}/history`),api<Project[]>('/projects')])
      .then(([history,projects])=>{if(!closed){setRuns(history.runs);setName(projects.find(p=>p.id===projectId)?.name || 'Project');setError('');}})
      .catch(e=>{if(!closed)setError(e.message);});
    void load();const timer=window.setInterval(()=>void load(),5000);
    return ()=>{closed=true;window.clearInterval(timer);};
  },[projectId]);
  return <main className="project-tree-page"><div className="panel-head"><h1>{name} · Cây run</h1>
    <a href={`/?project=${projectId}&view=run`}>Quay về project</a></div>
    {error && <p role="alert">{error}</p>}
    <ProjectRunTree runs={runs} selectedId={null} large onSelect={id=>{window.location.href=`/?project=${projectId}&run=${id}`;}}/>
  </main>;
}
