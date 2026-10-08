import {Resource} from './api';
import ImportedSource from './ImportedSource';
import {statusText} from './sourceStatus';

export default function SourceDetails({projectId,resource,busy,onEdit}:{
  projectId:string;resource:Resource;busy:boolean;onEdit:(resource:Resource)=>void;
}) {
  return <article className="resource">
    <div className="panel-head"><h3>{resource.title}</h3><button disabled={busy} onClick={()=>onEdit(resource)}>{resource.attachment ? 'Thay file' : 'Sửa nguồn'}</button></div>
    <p className="source-meta">{resource.kind} · v{resource.version} · {statusText(resource.status)}</p>
    <code className="source-id">{resource.id}</code>
    {resource.file_path && <div className="stack"><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}`} target="_blank" rel="noreferrer">Mở file nguồn ↗</a><code className="source-id">{resource.file_path}</code></div>}
    {resource.url && <a href={resource.url} target="_blank" rel="noreferrer">Mở nguồn ↗</a>}
    {resource.attachment && <ImportedSource key={`${resource.id}:${resource.version}`} projectId={projectId} resource={resource}/>}
    <details><summary>Xem nội dung và dấu kiểm tra</summary><pre>{resource.content || 'Chưa cung cấp nội dung nguồn. App chưa tải trang này.'}</pre><code className="source-id">SHA256 {resource.content_sha256}</code></details>
  </article>;
}
