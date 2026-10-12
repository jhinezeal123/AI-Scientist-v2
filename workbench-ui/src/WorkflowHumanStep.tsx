import {useState} from 'react';
import {HumanInput,stages} from './projectWorkflows';

export default function WorkflowHumanStep({input,disabled,answer}:{input:HumanInput;disabled:boolean;answer:(result:unknown)=>void}){
  const [title,setTitle]=useState(''),[text,setText]=useState(''),[reason,setReason]=useState(''),[json,setJson]=useState('{}');
  const [messageId]=useState(()=>crypto.randomUUID().replaceAll('-',''));
  const proposal=input.prompt.kind==='proposal';
  const candidate=input.prompt.candidate as {version?:number;body?:{paraphrase?:string;objective?:string;implementation_steps?:string[]}}|undefined;
  const review=input.prompt.kind==='review'||input.stage==='approval';
  return <article className="workflow-human"><span className="eyebrow">CHỜ BẠN</span><h3>{proposal?'Thiết kế proposal':input.stage==='run_approval'?'Duyệt bắt đầu run':stages.find(([s])=>s===input.stage)?.[1]||input.stage}</h3>
    {proposal?<><p>Proposal v{candidate?.version} · {candidate?.body?.paraphrase}</p>{candidate?.body?.objective&&<p>{candidate.body.objective}</p>}
      {input.prompt.questions?.length? <><p className="alert">Agent cần bạn làm rõ trước khi duyệt.</p><ul>{input.prompt.questions.map((question,i)=><li key={i}>{question}</li>)}</ul></>:null}
      <details><summary>Xem proposal đầy đủ</summary><pre>{JSON.stringify(candidate?.body,null,2)}</pre></details>
      <label>Nhắn lại cho agent<textarea rows={3} value={text} onChange={e=>setText(e.target.value)} placeholder="Làm rõ yêu cầu hoặc yêu cầu chỉnh proposal…"/></label>
      <button disabled={disabled||!text.trim()} onClick={()=>answer({message:text.trim(),request_id:messageId})}>Gửi và lập lại proposal</button>
      <p className="muted">Gửi tin nhắn sẽ thay thế proposal hiện tại. Chỉ proposal mới đủ rõ mới có thể được duyệt.</p>
      <div className="actions"><button className="primary" disabled={disabled||!input.prompt.approval_allowed||!!text.trim()} onClick={()=>answer({approve:true,reason:'Operator approved this exact candidate'})}>Duyệt proposal và tiếp tục</button><button disabled={disabled||!input.prompt.approval_allowed} onClick={()=>answer({approve:false,reason:'Operator rejected this candidate'})}>Từ chối</button></div>
    </>:review?<><details open><summary>Xem nội dung cần duyệt</summary><pre>{JSON.stringify(input.prompt.candidate||input.prompt.prompt,null,2)}</pre></details><label>Ghi chú<input value={reason} onChange={e=>setReason(e.target.value)} placeholder="Có thể để trống"/></label><div className="actions"><button className="primary" disabled={disabled} onClick={()=>answer({approve:true,reason:reason.trim()||'Operator approved this exact candidate'})}>Duyệt và tiếp tục</button><button disabled={disabled} onClick={()=>answer({approve:false,reason:reason.trim()||'Operator rejected this candidate'})}>Từ chối</button></div></>:input.stage==='ideation'?<><label>Tên idea<input value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Giả thuyết và mục tiêu<textarea rows={4} value={text} onChange={e=>setText(e.target.value)}/></label><button className="primary" disabled={disabled||!title.trim()||!text.trim()} onClick={()=>answer({title,text})}>Gửi idea</button></>:<><details><summary>Yêu cầu</summary><pre>{JSON.stringify(input.prompt,null,2)}</pre></details><label>Kết quả<textarea rows={5} value={json} onChange={e=>setJson(e.target.value)}/></label><button disabled={disabled} onClick={()=>answer(JSON.parse(json))}>Gửi và tiếp tục</button></>}
  </article>;
}

