import {useState} from 'react';
import {Idea, Proposal, Resource} from './api';

type Props = {idea?: Idea; proposals: Proposal[]; resources:Resource[]; busy: boolean;
  onAnswer: (proposal: Proposal, text: string) => Promise<void>;
  onContinue: (proposal: Proposal) => Promise<void>;
  onApprove: (proposal: Proposal) => Promise<void>};

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
        <h3>Split / subset / seed</h3><p>{latest.body.split?.method}</p><p className="muted">Group: {latest.body.split?.group_key} · seed: {latest.body.split?.seed}</p><p>{latest.body.split?.subset}</p>
        <h3>Metric</h3><p>{latest.body.metric?.name} · {latest.body.metric?.direction === 'minimize' ? 'Càng thấp càng tốt' : 'Càng cao càng tốt'}</p><p>{latest.body.metric?.definition}</p>
        <h3>Cách triển khai</h3><ol>{latest.body.implementation_steps?.map((step,i) => <li key={i}>{step}</li>)}</ol>
        <h3>Ngân sách mỗi lượt chạy</h3><div className="budget-grid"><span>Thời gian training<strong>{latest.body.budget?.training_seconds} giây</strong></span><span>Outputs<strong>{((latest.body.budget?.output_bytes || 0)/1000000).toFixed(1)} MB</strong></span></div>
        <p className="muted">Bạn quyết định từng lượt tạo code và chạy Kaggle, không giới hạn tổng số lượt.</p>
        <h3>Đầu ra dự kiến</h3><ul>{latest.body.expected_outputs?.map((output,i) => <li key={i}>{output}</li>)}</ul>
        <code className="source-id">Context SHA256 {latest.context_sha256}</code>
        {latest.state === 'AWAITING_APPROVAL' && <div className="stack"><p className="muted">Duyệt sẽ pin proposal này và tạo run đầu tiên. Các lượt tiếp theo dùng cùng phạm vi đã duyệt; mount được xác minh trước submit.</p><button className="primary" disabled={busy || idea?.state === 'PLANNING'} onClick={() => void onApprove(latest).catch(() => {})}>Duyệt proposal v{latest.version}</button></div>}
        {latest.state === 'APPROVED' && <p className="alert">Đã duyệt. Mở tab Run để tạo hoặc xem code, notebook và preflight. Chưa tự gửi Kaggle.</p>}
      </>}
      {answered && <div className="stack"><p className="alert">Câu trả lời đã được lưu. Tiếp tục để Codex đọc câu trả lời và lập proposal v{latest.version + 1} từ các nguồn của v{latest.version}.</p>
        <button type="button" className="primary" disabled={busy || idea?.state === 'PLANNING'}
          onClick={() => void onContinue(latest).catch(() => {})}>Tiếp tục lập proposal v{latest.version + 1}</button></div>}
      {latest.state === 'STALE' && !answered && <p className="alert error">Proposal đã cũ. Chọn nguồn hiện hành và lập proposal lại trước khi duyệt.</p>}
    </article>}
  </section>;
}
