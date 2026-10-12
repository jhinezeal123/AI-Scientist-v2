import {useEffect,useState} from 'react';
import {agentCall} from './agentApi';

type Candidate={id:string;ordinal:number;iteration:number;status:string;idea:{title:string;text:string}|null;reason?:string;created_at:string};
const names:Record<string,string>={pending:'Đang tạo',generated:'Chờ novelty',eligible:'Đủ điều kiện',selected:'Đã chọn',unselected:'Lưu để tham khảo',duplicate:'Trùng idea trước',rejected:'Novelty chưa đạt'};
export default function IdeaArchive({projectId,revision}:{projectId:string;revision:string}){
  const [rows,setRows]=useState<Candidate[]>([]),[error,setError]=useState('');
  useEffect(()=>{let closed=false;void agentCall<Candidate[]>('/projects/'+projectId+'/idea-archive').then(value=>{if(!closed){setRows(value);setError('');}}).catch(e=>{if(!closed)setError(e.message);});return()=>{closed=true;};},[projectId,revision]);
  return <details className="idea-archive"><summary>Archive idea · {rows.length} ứng viên</summary>
    <p className="muted">Ứng viên đã chọn, chưa chọn, trùng và bị loại được giữ trong project. Agent đọc lại lịch sử này khi sinh idea ở vòng tiếp theo.</p>
    {error&&<p role="alert">{error}</p>}{!rows.length&&<p>Chưa có ứng viên trong archive.</p>}
    {rows.slice().reverse().map(row=><article key={row.id}><strong>{row.idea?.title||'Đang tạo ứng viên'}</strong><p>{names[row.status]||row.status} · vòng {row.iteration+1} · ứng viên {row.ordinal+1}</p>{row.reason&&<p className="muted">{row.reason}</p>}{row.idea&&<details><summary>Xem idea</summary><p className="pre-wrap">{row.idea.text}</p></details>}</article>)}
  </details>;
}
