import {FormEvent,useState} from 'react';
import {api,Resource,RunOutput} from './api';

type Selection = {kind:'text'|'file';sha256:string;path?:string};
const choiceId=(choice:Selection)=>choice.kind==='text' ? 'text' : `file:${choice.path}`;
const suggestedTitle=(choice:Selection,runId:string)=>choice.kind==='text' ? `Output · Run ${runId.slice(0,8)}`
  : (choice.path!.split('/').at(-1) || '').replace(/\.[^.]+$/,'');

export default function OutputToLibrary({projectId,runId,output,disabled=false,onCopied}:{
  projectId:string;runId:string;output:RunOutput;disabled?:boolean;onCopied?:(resource:Resource)=>void;
}) {
  const choices:Selection[]=[...(output.summary_sha256 ? [{kind:'text' as const,sha256:output.summary_sha256}] : []),
    ...output.files.map(file=>({kind:'file' as const,path:file.path,sha256:file.sha256}))];
  const [selection,setSelection]=useState<Selection|null>(null);
  const [title,setTitle]=useState('');
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  const [copied,setCopied]=useState<Resource|null>(null);
  if (!choices.length)return null;
  function choose(choice:Selection) {
    setTitle(current=>!current.trim() || (selection && current===suggestedTitle(selection,runId))
      ? suggestedTitle(choice,runId) : current);
    setSelection(choice);setError('');
  }
  const changed=!!selection && !choices.some(choice=>choiceId(choice)===choiceId(selection) && choice.sha256===selection.sha256);
  async function copy(event:FormEvent) {
    event.preventDefault();
    if (!selection || pending || disabled || changed || !title.trim())return;
    setPending(true);setError('');
    try {
      const resource=await api<Resource>(`/projects/${projectId}/runs/${runId}/output/library`,'POST',
        {...selection,title:title.trim()});
      setCopied(resource);setSelection(null);onCopied?.(resource);
    } catch (error) {setError(error instanceof Error ? error.message : String(error));}
    finally {setPending(false);}
  }
  return <div className="output-copy">
    {!selection ? <button type="button" disabled={disabled || pending} onClick={()=>{
      setTitle(suggestedTitle(choices[0],runId));setSelection(choices[0]);setError('');setCopied(null);
    }}>Thêm vào Library</button> : <form className="stack" aria-label="Copy Output vào Library" onSubmit={event=>void copy(event)}>
      <label>Kết quả cần copy<select value={choiceId(selection)} disabled={disabled || pending}
        onChange={event=>{const choice=choices.find(choice=>choiceId(choice)===event.target.value);if (choice)choose(choice);}}>
        {!choices.some(choice=>choiceId(choice)===choiceId(selection)) && <option value={choiceId(selection)}>Kết quả đã thay đổi</option>}
        {choices.map(choice=><option key={choiceId(choice)} value={choiceId(choice)}>
          {choice.kind==='text' ? 'Nội dung Output' : choice.path}
        </option>)}
      </select></label>
      <label>Tiêu đề nguồn<input required maxLength={240} value={title} disabled={disabled || pending}
        onChange={event=>setTitle(event.target.value)}/></label>
      <small className="muted">Tạo bản copy riêng trong Library của project này.</small>
      {changed && <p role="alert" className="alert error">Output đã thay đổi. Đóng và mở lại form để chọn kết quả hiện hành.</p>}
      <div className="actions"><button type="submit" className="primary" disabled={disabled || pending || changed || !title.trim()}>
        {pending ? 'Đang copy…' : 'Copy vào Library'}</button>
        <button type="button" disabled={pending} onClick={()=>{setSelection(null);setError('');}}>Đóng</button></div>
    </form>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {copied && <p role="status">Đã thêm <strong>{copied.title}</strong> · v{copied.version}.{' '}
      <a href={`/?project=${projectId}&view=library`}>Mở Library ↗</a></p>}
  </div>;
}
