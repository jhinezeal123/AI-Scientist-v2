import {FormEvent, useState} from 'react';
import {Project} from './api';

export default function ProjectDeletion({project, disabled, busy, onDelete}: {
  project:Project;disabled:boolean;busy:boolean;onDelete:(project:Project)=>void;
}) {
  const [confirming,setConfirming]=useState(false);
  const [name,setName]=useState('');
  function submit(event:FormEvent) {
    event.preventDefault();
    if (!disabled && name===project.name)onDelete(project);
  }
  return <div className="project-deletion">
    {!confirming ? <button type="button" className="danger" disabled={disabled} onClick={()=>setConfirming(true)}>Xóa project</button>
      : <form className="delete-confirmation" aria-label="Xác nhận xóa project" onSubmit={submit}>
        <p>Xóa vĩnh viễn <strong>{project.name}</strong>?</p>
        <p>Toàn bộ nguồn, idea, run và artifacts trong thư mục project sẽ bị xóa khỏi máy. Không thể khôi phục trong ứng dụng.</p>
        <label>Nhập tên project để xác nhận<input autoFocus value={name} maxLength={120} disabled={busy} onChange={e=>setName(e.target.value)} autoComplete="off"/></label>
        <div className="actions"><button type="submit" className="danger" disabled={disabled || name!==project.name}>{busy ? 'Đang xóa…' : 'Xóa vĩnh viễn'}</button>
          <button type="button" disabled={busy} onClick={()=>{setConfirming(false);setName('');}}>Hủy</button></div>
      </form>}
  </div>;
}
