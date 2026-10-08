export default function ArtifactLinks({projectId,runId,names}:{projectId:string;runId:string;names:string[]}) {
  return <div className="stack">{names.map(name=>
    <a key={name} href={`/api/projects/${projectId}/runs/${runId}/artifacts/${name.split('/').map(encodeURIComponent).join('/')}`} target="_blank" rel="noreferrer">{name} ↗</a>)}</div>;
}
