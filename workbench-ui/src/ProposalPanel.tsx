import {useState} from 'react';
import {Idea, Proposal, Resource, modeLabel} from './api';
import ResearchScope from './ResearchScope';

type Props = {idea?: Idea; proposals: Proposal[]; resources:Resource[]; busy: boolean;
  onOpenParent:(id:string)=>void;
  onReplan:()=>Promise<void>;
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

export default function ProposalPanel({idea,proposals,resources,busy,onOpenParent,onAnswer,onContinue,onApprove,onReplan}:Props) {
  const [answer,setAnswer] = useState('');
  const latest = proposals.filter(p => p.idea_id === idea?.id).sort((a,b) => b.version-a.version)[0];
  const pinnedIdea=latest?.context_snapshot.idea;
  const settingsMatch=!!idea && (pinnedIdea?.mode || 'training_research')===idea.mode
    && (pinnedIdea?.desired_output || '')===idea.desired_output;
  const changedSources=latest?.context_snapshot.resources.filter(source=>!resources.some(current=>
    !current.deletion_pending && current.id===source.id && current.version===source.version && current.content_sha256===source.content_sha256)) || [];
  const answered = latest?.state === 'STALE' && latest.body.needs_clarification
    && idea?.conversation.some(message => message.role === 'user' && message.reply_to === latest.id)
    && latest.context_snapshot.idea.text === idea?.text
    && settingsMatch
    && latest.context_snapshot.resources.every(source => resources.some(current =>
      !current.deletion_pending && current.id === source.id && current.version === source.version && current.content_sha256 === source.content_sha256));
  return <section className="panel proposal-panel"><div className="panel-head"><h2>Trao đổi và proposal</h2>{idea && <span className="state-tag">{idea.state==='NEEDS_REVIEW' ? 'Cần xem lại proposal' : idea.state}</span>}</div>
    {!idea && <p className="empty">Chọn một idea đã lưu để lập proposal.</p>}
    {idea?.state === 'PLANNING' && <p role="status" className="alert">Codex đang đọc nguồn và lập proposal. Bạn vẫn có thể xem Library; chưa tạo code hoặc chạy notebook.</p>}
    {idea?.error && <p role="alert" className="alert error">{idea.error}</p>}
    {idea?.variant && <div className="context variant-context">
      <h3>Idea biến thể từ Run {idea.variant.parent_run_id.slice(0,8)}</h3>
      {idea.variant.parent_deleted_at
        ? <p role="status" className="muted">Run cha đang ẩn. Khôi phục ở tab Run để mở lại.</p>
        : <button type="button" onClick={()=>onOpenParent(idea.variant!.parent_run_id)}>Mở Run cha</button>}
      <p><strong>Mục đích mới: </strong>{idea.variant.purpose}</p>
      <p><strong>Thay đổi: </strong>{idea.variant.change_summary}</p>
      <small className="muted">Proposal cha {idea.variant.parent_proposal_id} · v{idea.variant.parent_proposal_version} · context {idea.variant.baseline.parent.context_sha256}</small>
      <h4>Baseline đã ghim</h4>
      {!idea.variant.baseline.text_files.some(file=>file.available) && <p className="muted">Run cha không có report/code text đọc được; metadata và nguồn đã duyệt vẫn được giữ.</p>}
      {idea.variant.baseline.text_files.map(file=><div className="context-source" key={file.stage_path}>
        <strong>{file.kind}</strong><small>{file.available ? `${file.bytes} bytes · SHA256 ${file.sha256}` : `Không cấp được: ${file.reason}`}</small>
        {file.available && <code className="source-id">{file.stage_path}</code>}
      </div>)}
      {!!idea.variant.baseline.parent.sources.length && <p className="muted">Nguồn cha: {idea.variant.baseline.parent.sources.map(source=>`${source.title} · v${source.version} · ${source.content_sha256.slice(0,12)}`).join(' | ')}</p>}
    </div>}
    {idea?.conversation.map((message,index) => <article className="conversation" key={index}><span className="source-meta">{message.role === 'user' ? 'Bạn' : `Codex · v${message.version}`}</span>
      {message.role === 'user' ? <pre>{message.text}</pre> : message.body.questions.length === 1 ? <p>{message.body.questions[0]}</p>
        : message.body.questions.length > 1 ? <ol>{message.body.questions.map((question,i) => <li key={i}>{question}</li>)}</ol>
        : <p>{message.body.paraphrase}</p>}
    </article>)}
    {latest && <article className="proposal"><div className="panel-head"><h3>Proposal v{latest.version}</h3><span className="state-tag">{answered ? 'Đã trả lời' : latest.state}</span></div>
      <code className="source-id">{latest.id}</code>
      <p className="mode-tag" data-mode={pinnedIdea?.mode}>{modeLabel(pinnedIdea?.mode)}</p>
      {pinnedIdea?.mode==='etc' && <><h3>Đầu ra user yêu cầu</h3><pre>{pinnedIdea.desired_output}</pre></>}
      {!latest.body.needs_clarification && <p>{latest.body.paraphrase}</p>}
      {latest.state === 'NEEDS_CLARIFICATION' && <form className="stack" onSubmit={event => {event.preventDefault(); void onAnswer(latest,answer).then(() => setAnswer('')).catch(() => {});}}>
        <label>Trả lời câu hỏi<textarea value={answer} rows={5} maxLength={20000} required onChange={e => setAnswer(e.target.value)}/></label>
        <button className="primary" disabled={busy || !answer.trim()}>Lưu câu trả lời</button><small className="muted">Sau khi lưu, bấm “Lập proposal bằng Codex” để tạo phiên bản mới.</small></form>}
      {!latest.body.needs_clarification && <>
        <h3>Mục tiêu</h3><p>{latest.body.objective}</p>
        <h3>Nguồn đã chọn</h3>{latest.context_snapshot.resources.map(source => <div className="context-source" key={source.id}><strong>{source.title}</strong><small>v{source.version} · {source.status}</small><code className="source-id">{source.file_path || source.id}</code></div>)}
        {latest.body.split && <><h3>Chia dữ liệu</h3><Details value={latest.body.split}/></>}
        {latest.body.metric && <><h3>Cách đánh giá</h3><Details value={latest.body.metric}/></>}
        <h3>Cách triển khai</h3><ol>{latest.body.implementation_steps?.map((step,i) => <li key={i}>{step}</li>)}</ol>
        {latest.body.budget && Object.keys(latest.body.budget).some(key=>!['coder_calls','training_attempts'].includes(key)) && <><h3>Giới hạn bạn yêu cầu</h3><Details value={latest.body.budget}/></>}
        <p className="muted">Bạn quyết định từng lượt Working, không giới hạn tổng số lượt.</p>
        {pinnedIdea?.mode!=='etc' && latest.body.research && <><h3>Phạm vi Research</h3>
          <ResearchScope plan={latest.body.research}/><p className="muted">Các phần này được ghim khi duyệt. Đổi yêu cầu trong idea và lập proposal mới nếu muốn thêm hoặc bỏ đầu ra.</p></>}
        {!!latest.body.expected_outputs?.length && <><h3>Đầu ra dự kiến</h3><ul>{latest.body.expected_outputs.map((output,i) => <li key={i}>{output}</li>)}</ul></>}
        <code className="source-id">Context SHA256 {latest.context_sha256}</code>
        {latest.state === 'AWAITING_APPROVAL' && <div className="stack"><p className="muted">Duyệt sẽ lưu phạm vi công việc và tạo run đầu tiên. Agent kiểm tra môi trường và thực hiện trong phiên Working.</p><button className="primary" disabled={busy || idea?.state === 'PLANNING'} onClick={() => void onApprove(latest).catch(() => {})}>Duyệt proposal v{latest.version}</button></div>}
        {latest.state === 'APPROVED' && <p className="alert">{pinnedIdea?.mode==='etc'
          ? 'Đã duyệt proposal Etc. Mở tab Run và bấm Bắt đầu Working; kết quả sẽ nằm trong Output.'
          : 'Đã duyệt. Mở tab Run và bấm Bắt đầu Working để thực hiện công việc trên Kaggle.'}</p>}
      </>}
      {answered && <div className="stack"><p className="alert">Câu trả lời đã được lưu. Tiếp tục để Codex đọc câu trả lời và lập proposal v{latest.version + 1} từ các nguồn của v{latest.version}.</p>
        <button type="button" className="primary" disabled={busy || idea?.state === 'PLANNING'}
          onClick={() => void onContinue(latest).catch(() => {})}>Tiếp tục lập proposal v{latest.version + 1}</button></div>}
      {latest.state === 'STALE' && !answered && <div className="stack"><p className="alert error">Proposal cần xem lại.{changedSources.length
        ? ` Nguồn đã đổi phiên bản hoặc bị xóa: ${changedSources.map(source=>source.title).join(', ')}.`
        : !settingsMatch ? ' Mode hoặc đầu ra mong muốn đã thay đổi.' : ' Nội dung idea hoặc trao đổi đã thay đổi.'} Bản proposal cũ vẫn được lưu; kiểm tra nguồn đang chọn rồi lập bản mới trước khi duyệt.</p>
        {idea?.state!=='APPROVED' && <button type="button" className="primary" disabled={busy}
          onClick={()=>void onReplan()}>Lập lại proposal từ nguồn đang chọn</button>}</div>}
    </article>}
    {idea?.state==='FAILED' && <div className="stack"><p className="muted">Trao đổi đã lưu sẽ được gửi cùng các nguồn đang chọn. Tiếp tục là yêu cầu một lượt lập proposal mới.</p>
      <button type="button" className="primary" disabled={busy} onClick={()=>void onReplan()}>Tiếp tục lập proposal</button></div>}
  </section>;
}
