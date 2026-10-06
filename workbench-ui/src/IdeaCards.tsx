import {useState} from 'react';
import {Idea,ideaTitle} from './api';

const labels:Record<string,string>={
  DRAFT:'Bản nháp', PLANNING:'Đang lập proposal', NEEDS_CLARIFICATION:'Cần trả lời',
  AWAITING_APPROVAL:'Chờ duyệt', APPROVED:'Đã duyệt', FAILED:'Có lỗi',
};

function TitleEditor({idea,busy,onRename}:{idea:Idea;busy:boolean;onRename:(idea:Idea,title:string)=>Promise<void>}) {
  const [title,setTitle]=useState(idea.title);
  return <form className="stack" onSubmit={event=>{event.preventDefault();void onRename(idea,title);}}>
    <label>Đổi tiêu đề<input value={title} required maxLength={80} disabled={busy}
      placeholder="Đặt tiêu đề ngắn gọn" onChange={event=>setTitle(event.target.value)}/></label>
    <div className="actions"><button disabled={busy || !title.trim() || title.trim()===idea.title}>Lưu tiêu đề</button></div>
  </form>;
}

export default function IdeaCards({ideas,selectedId,busy,onSelect,onEdit,onRename}:{
  ideas:Idea[];selectedId:string;busy:boolean;onSelect:(id:string)=>void;onEdit:(idea:Idea)=>void;
  onRename:(idea:Idea,title:string)=>Promise<void>;
}) {
  const selected=ideas.find(idea=>idea.id===selectedId);
  return <div className="saved-ideas">
    <div className="panel-head section-heading"><h2>Idea đã lưu</h2>
      {!!ideas.length && <span className="muted">{ideas.length} idea</span>}</div>
    {!ideas.length && <p className="empty">Chưa có idea.</p>}
    {!!ideas.length && <div className="idea-cards" aria-label="Danh sách idea">
      {ideas.map(idea=><button type="button" key={idea.id}
        className={`idea-card ${selectedId===idea.id ? 'selected' : ''}`}
        aria-expanded={selectedId===idea.id} aria-controls="idea-detail"
        onClick={()=>onSelect(selectedId===idea.id ? '' : idea.id)}>
        <span className="idea-alias" title={ideaTitle(idea)}>{ideaTitle(idea)}</span>
        {!idea.title && <small className="idea-preview" title={idea.text.slice(0,160)}>{idea.text.slice(0,80)}</small>}
        <span className="idea-card-status" data-state={idea.state}>
          <span className="idea-status-dot" aria-hidden="true"/>{labels[idea.state] || idea.state}
        </span>
      </button>)}
    </div>}
    {!!ideas.length && !selected && <p className="muted">Chọn một idea để xem nội dung và proposal.</p>}
    {selected && <article className="resource idea-detail" id="idea-detail"
      aria-label={`Chi tiết idea: ${ideaTitle(selected)}`}>
      <div className="panel-head"><h3>{ideaTitle(selected)}</h3>
        <button type="button" onClick={()=>onSelect('')}>Đóng chi tiết</button></div>
      <TitleEditor key={`${selected.id}:${selected.title}`} idea={selected} busy={busy} onRename={onRename}/>
      <p className="source-meta">{labels[selected.state] || selected.state} · {new Date(selected.created_at).toLocaleString('vi-VN')}</p>
      <pre>{selected.text}</pre><code className="source-id">{selected.id}</code>
      <button type="button" disabled={busy || selected.state==='PLANNING' || selected.state==='APPROVED'}
        onClick={()=>onEdit(selected)}>Sửa idea</button>
    </article>}
  </div>;
}
