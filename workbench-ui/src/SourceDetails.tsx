import {useState} from 'react';
import {Resource} from './api';
import ImportedSource from './ImportedSource';
import {statusText} from './sourceStatus';

export default function SourceDetails({projectId,resource,busy,deletionBlocked,onEdit,onClose,onDelete}:{
  projectId:string;resource:Resource;busy:boolean;deletionBlocked:boolean;
  onEdit:(resource:Resource)=>void;onClose:()=>void;onDelete:(resource:Resource)=>Promise<void>;
}) {
  const [confirmDelete,setConfirmDelete]=useState(false);
  return <article className="resource source-detail" id="source-detail" aria-label={`Chi tiết nguồn: ${resource.title}`}>
    <div className="panel-head"><h3>{resource.title}</h3><button type="button" onClick={onClose}>Đóng chi tiết</button></div>
    {resource.deletion_pending ? <p role="alert" className="alert error">{resource.deletion_error || 'Nguồn đang được xóa.'}</p> : <>
    <p className="source-meta">{resource.kind} · v{resource.version} · {statusText(resource.status)}</p>
    <code className="source-id">{resource.id}</code>
    {resource.file_path && <div className="stack"><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}`} target="_blank" rel="noreferrer">Mở file nguồn ↗</a><code className="source-id">{resource.file_path}</code></div>}
    {!!(resource.urls?.length || resource.url) && <div className="stack">{(resource.urls?.length ? resource.urls : [resource.url!]).map(url=>
      <a key={url} href={url} target="_blank" rel="noreferrer">{url} ↗</a>)}</div>}
    {resource.attachment && <ImportedSource key={`${resource.id}:${resource.version}`} projectId={projectId} resource={resource}/>}
    <details><summary>Xem nội dung và dấu kiểm tra</summary><pre>{resource.content || 'Chưa cung cấp nội dung nguồn. App chưa tải trang này.'}</pre><code className="source-id">SHA256 {resource.content_sha256}</code></details>
    </>}
    <div className="actions source-actions">
      {!resource.deletion_pending && <button type="button" disabled={busy} onClick={()=>onEdit(resource)}>{resource.attachment ? 'Thay file' : 'Sửa nguồn'}</button>}
      <button type="button" className="danger-button" disabled={busy || deletionBlocked} onClick={()=>setConfirmDelete(true)}>
        {resource.deletion_pending ? 'Thử xóa lại' : 'Xóa nguồn'}
      </button>
    </div>
    {deletionBlocked && <p className="muted">Chờ agent kết thúc trước khi xóa nguồn.</p>}
    {confirmDelete && <div className="delete-confirmation" role="group" aria-label="Xác nhận xóa nguồn">
      <p>Xóa vĩnh viễn <strong>{resource.title}</strong> cùng file gốc, tất cả phiên bản và bản sao nguồn trong thư mục làm việc của agent. Không thể khôi phục.</p>
      <p className="muted">Proposal dùng nguồn này cần lập lại. Muốn chạy lại một run cũ dùng nguồn này, bạn cần nhập nguồn lại và lập proposal mới.</p>
      <div className="actions"><button type="button" className="danger-button" disabled={busy || deletionBlocked} onClick={()=>void onDelete(resource)}>Xóa vĩnh viễn</button>
        <button type="button" disabled={busy} onClick={()=>setConfirmDelete(false)}>Hủy xóa</button></div>
    </div>}
  </article>;
}
