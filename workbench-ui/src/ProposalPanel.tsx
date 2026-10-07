import {useState} from 'react';
import {Idea, Proposal, Resource} from './api';

type Props = {idea?: Idea; proposals: Proposal[]; resources:Resource[]; busy: boolean;
  onAnswer: (proposal: Proposal, text: string) => Promise<void>;
  onContinue: (proposal: Proposal) => Promise<void>;
  onApprove: (proposal: Proposal) => Promise<void>};

const labels:Record<string,string> = {method:'Cách chia',group_key:'Nhóm',subset:'Phạm vi dữ liệu',seed:'Seed',
  name:'Tên',direction:'Hướng đánh giá',definition:'Định nghĩa',training_seconds:'Thời gian training (giây)',
  execution_seconds:'Thời gian thực thi (giây)',output_bytes:'Dung lượng đầu ra (byte)'};
function Details({value}:{value:string|Record<string,unknown>}) {
  if (typeof value === 'string')return <p>{value}</p>;
  return <div className="stack">{Object.entries(value).filter(([key])=>!['coder_calls','training_attempts'].includes(key))
    .map(([key,item])=><p key={key}><strong>{labels[key] || key}: </strong>{typeof item==='string' ? item : JSON.stringify(item)}</p>)}</div>;
}

export default function ProposalPanel({idea,proposals,resources,busy,onAnswer,onContinue,onApprove}:Props) {
  const [answer,setAnswer] = useState('');
  const latest = proposals.filter(p => p.idea_id === idea?.id).sort((a,b) => b.version-a.version)[0];
  const answered = latest?.state === 'STALE' && latest.body.needs_clarification
    && idea?.conversation.some(message => message.role === 'user' && message.reply_to === latest.id)
    && latest.context_snapshot.idea.text === idea?.text
    && latest.context_snapshot.resources.every(source => resources.some(current =>
      current.id === source.id && current.version === source.version && current.content_sha256 === source.content_sha256));
  return <section className="panel proposal-panel"><div className="panel-head"><h2>Trao đổi và proposal</h2>{idea && <span className="state-tag">{idea.state}</span>}</div>
    {!idea && <p className="empty">Chọn một idea đã lưu để lập proposal.</p>}
    {idea?.state === 'PLANNING' && <p role="status" className="alert">Codex đang đọc nguồn và lập proposal. Bạn vẫn có thể xem Library; chưa tạo code hoặc chạy notebook.</p>}
    {idea?.error && <p role="alert" className="alert error">{idea.error}</p>}
    {idea?.conversation.map((message,index) => <article className="conversation" key={index}><span className="source-meta">{message.role === 'user' ? 'Bạn' : `Codex · v${message.version}`}</span>
      {message.role === 'user' ? <pre>{message.text}</pre> : <><p>{message.body.paraphrase}</p>{message.body.questions.length > 0 && <ol>{message.body.questions.map((question,i) => <li key={i}>{question}</li>)}</ol>}</>}
    </article>)}
    {latest && <article className="proposal"><div className="panel-head"><h3>Proposal v{latest.version}</h3><span className="state-tag">{answered ? 'Đã trả lời' : latest.state}</span></div>
      <code className="source-id">{latest.id}</code>
      <p>{latest.body.paraphrase}</p>
      {latest.state === 'NEEDS_CLARIFICATION' && <form className="stack" onSubmit={event => {event.preventDefault(); void onAnswer(latest,answer).then(() => setAnswer('')).catch(() => {});}}>
        <label>Trả lời câu hỏi<textarea value={answer} rows={5} maxLength={20000} required onChange={e => setAnswer(e.target.value)}/></label>
        <button className="primary" disabled={busy || !answer.trim()}>Lưu câu trả lời</button><small className="muted">Sau khi lưu, bấm “Lập proposal bằng Codex” để tạo phiên bản mới.</small></form>}
      {!latest.body.needs_clarification && <>
        <h3>Mục tiêu</h3><p>{latest.body.objective}</p>
        <h3>Data và nguồn được pin</h3>{latest.context_snapshot.resources.map(source => <div className="context-source" key={source.id}><strong>{source.title}</strong><small>v{source.version} · {source.status}</small><code className="source-id">{source.id}</code></div>)}
        {latest.body.split && <><h3>Chia dữ liệu</h3><Details value={latest.body.split}/></>}
        {latest.body.metric && <><h3>Cách đánh giá</h3><Details value={latest.body.metric}/></>}
        <h3>Cách triển khai</h3><ol>{latest.body.implementation_steps?.map((step,i) => <li key={i}>{step}</li>)}</ol>
        {latest.body.budget && Object.keys(latest.body.budget).some(key=>!['coder_calls','training_attempts'].includes(key)) && <><h3>Giới hạn bạn yêu cầu</h3><Details value={latest.body.budget}/></>}
        <p className="muted">Bạn quyết định từng lượt Working, không giới hạn tổng số lượt.</p>
        {!!latest.body.expected_outputs?.length && <><h3>Đầu ra dự kiến</h3><ul>{latest.body.expected_outputs.map((output,i) => <li key={i}>{output}</li>)}</ul></>}
        <code className="source-id">Context SHA256 {latest.context_sha256}</code>
        {latest.state === 'AWAITING_APPROVAL' && <div className="stack"><p className="muted">Duyệt sẽ lưu phạm vi công việc và tạo run đầu tiên. Agent kiểm tra môi trường và thực hiện trong phiên Working.</p><button className="primary" disabled={busy || idea?.state === 'PLANNING'} onClick={() => void onApprove(latest).catch(() => {})}>Duyệt proposal v{latest.version}</button></div>}
        {latest.state === 'APPROVED' && <p className="alert">Đã duyệt. Mở tab Run và bấm Bắt đầu Working để thực hiện công việc trên Kaggle.</p>}
      </>}
      {answered && <div className="stack"><p className="alert">Câu trả lời đã được lưu. Tiếp tục để Codex đọc câu trả lời và lập proposal v{latest.version + 1} từ các nguồn của v{latest.version}.</p>
        <button type="button" className="primary" disabled={busy || idea?.state === 'PLANNING'}
          onClick={() => void onContinue(latest).catch(() => {})}>Tiếp tục lập proposal v{latest.version + 1}</button></div>}
      {latest.state === 'STALE' && !answered && <p className="alert error">Proposal đã cũ. Chọn nguồn hiện hành và lập proposal lại trước khi duyệt.</p>}
    </article>}
  </section>;
}
