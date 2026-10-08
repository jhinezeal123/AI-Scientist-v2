import {useState} from 'react';
import {Resource} from './api';
import SourceDetails from './SourceDetails';
import {statusText} from './sourceStatus';

export default function SourceCards({projectId,resources,busy,deletionBlocked,onEdit,onDelete}:{
  projectId:string;resources:Resource[];busy:boolean;deletionBlocked:boolean;
  onEdit:(resource:Resource)=>void;onDelete:(resource:Resource)=>Promise<void>;
}) {
  const [selectedId,setSelectedId]=useState('');
  const selected=resources.find(resource=>resource.id===selectedId);
  return <>
    {!resources.length && <p className="empty">Chưa có nguồn. Thêm nội dung hoặc nhập file ở form bên cạnh.</p>}
    {!!resources.length && <div className="source-cards" aria-label="Danh sách nguồn">
      {resources.map(resource=><button type="button" key={resource.id}
        className={`source-card ${selectedId===resource.id ? 'selected' : ''}`}
        aria-expanded={selectedId===resource.id} aria-controls="source-detail"
        onClick={()=>setSelectedId(selectedId===resource.id ? '' : resource.id)}>
        <span className="source-alias" title={resource.title}>{resource.title}</span>
        <small className="source-card-status" data-pending={resource.deletion_pending || undefined}>
          {resource.deletion_pending ? 'Xóa chưa hoàn tất' : `v${resource.version} · ${statusText(resource.status)}`}
        </small>
      </button>)}
    </div>}
    {!!resources.length && !selected && <p className="muted">Chọn một nguồn để xem chi tiết.</p>}
    {selected && <SourceDetails key={`${selected.id}:${selected.version}`} projectId={projectId}
      resource={selected} busy={busy} deletionBlocked={deletionBlocked} onEdit={onEdit}
      onClose={()=>setSelectedId('')} onDelete={onDelete}/>}
  </>;
}
