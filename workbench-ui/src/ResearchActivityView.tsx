import {useEffect,useState} from 'react';
import type {Event,Snapshot} from './teamApi';
import {activityLabels,outputText,resultText,stageActivity,stageRecords} from './researchActivity';
import type {ActivityWorkflow} from './researchActivity';

type Binding={actor:'human'|'agent';seat:string;ask:boolean};
type Props={team:Snapshot;events:Event[];workflow:ActivityWorkflow|null;stages:readonly (readonly [string,string])[];bindings:Record<string,Binding>;onSelectSeat:(id:string)=>void;connectionError?:string};
const eventLabels:Record<string,string>={agent_queued:'Giao việc cho agent',agent_completed:'Agent trả kết quả',agent_result_invalid:'Yêu cầu sửa định dạng kết quả',human_completed:'Bạn đã trả lời'};
const shorten=(text:string,max:number)=>text.length>max?text.slice(0,max-1)+'…':text;
const time=(value:string)=>new Date(value).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const sessionLabels:Record<string,string>={STARTING:'Đang khởi động',RUNNING:'Đang chạy',STOPPING:'Đang dừng',DONE:'Hoàn tất',FAILED:'Lỗi',CANCELLED:'Đã hủy',UNKNOWN:'Cần đối soát'};

export default function ResearchActivityView({team,events,workflow,stages,bindings,onSelectSeat,connectionError}:Props){
  const [selected,setSelected]=useState(''),[tab,setTab]=useState<'activity'|'result'|'sessions'>('activity'),[taskId,setTaskId]=useState('');
  const [view,setView]=useState<'table'|'graph'>('table');
  const [narrow,setNarrow]=useState(()=>matchMedia('(max-width:640px)').matches);
  useEffect(()=>{const media=matchMedia('(max-width:640px)'),update=()=>setNarrow(media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  const defaultStage=stages.some(([id])=>id===workflow?.state.stage)?workflow!.state.stage:stages[0]?.[0];
  const stage=stages.some(([id])=>id===selected)?selected:defaultStage;
  useEffect(()=>{setSelected('');setTaskId('');setTab('activity');},[workflow?.id,team.id]);
  useEffect(()=>setTaskId(''),[stage]);
  const binding=bindings[stage],seat=team.spec.seats.find(row=>row.id===binding?.seat);
  const records=stageRecords(stage,workflow,team,events);
  const task=records.tasks.find(row=>row.id===taskId)||records.tasks.at(-1);
  const taskSessions=task?records.sessions.filter(session=>session.task_id?session.task_id===task.id:session.id===task.result?.session_id):[];
  const sessionIds=new Set(taskSessions.map(session=>session.id));
  const output=task?records.output.filter(event=>event.task_id?event.task_id===task.id:Boolean(event.session_id&&sessionIds.has(event.session_id))).filter(event=>event.kind==='output'&&outputText(event).trim()).slice(-8):[];
  const completed=stages.filter(([id])=>stageActivity(id,workflow)==='done').length;
  const currentLabel=stages.find(([id])=>id===workflow?.state.stage)?.[1];
  const state=stageActivity(stage,workflow);
  const columns=narrow?2:4,nodeWidth=174,nodeHeight=112,gapX=28,gapY=42,pad=20;
  const rows=Math.ceil(stages.length/columns),width=pad*2+columns*nodeWidth+(columns-1)*gapX,height=pad*2+rows*nodeHeight+(rows-1)*gapY;
  const positions=stages.map((_,index)=>{const row=Math.floor(index/columns),column=index%columns;return {x:pad+(row%2?columns-1-column:column)*(nodeWidth+gapX),y:pad+row*(nodeHeight+gapY)};});
  function choose(id:string){setSelected(id);setTaskId('');if(bindings[id].actor==='agent')onSelectSeat(bindings[id].seat);}
  return <div className="research-observer">
    <div className="observer-heading"><div><span className="eyebrow">HOẠT ĐỘNG AGENT</span><h3>{workflow?.state.status==='DONE'?'Luồng nghiên cứu đã hoàn tất':currentLabel?`${currentLabel} · ${activityLabels[stageActivity(workflow!.state.stage,workflow)]}`:'Luồng nghiên cứu của bạn'}</h3></div><span className={'observer-connection '+(connectionError?'offline':'')}><i/>{connectionError?'Không cập nhật được · trạng thái đã lưu':'Cập nhật mỗi 2 giây'}</span></div>
    <div className="observer-summary"><span>{completed}/{stages.length} giai đoạn hoàn tất</span><span>Mỗi giai đoạn có một người hoặc agent phụ trách</span></div>
    <div className="observer-layout"><div className="observer-map-column">
      <div className="observer-view-switch" role="group" aria-label="Cách xem hoạt động agent"><button aria-pressed={view==='table'} onClick={()=>setView('table')}>Danh sách</button><button aria-pressed={view==='graph'} onClick={()=>setView('graph')}>Sơ đồ</button></div>
      {view==='table'?<div className="observer-table-scroll"><table className="observer-table" aria-label="Hoạt động từng agent"><thead><tr><th>Giai đoạn / Agent</th><th>Harness / Model</th><th>Trạng thái</th><th>Lượt / Chờ</th></tr></thead><tbody>{stages.map(([id,label])=>{const actor=bindings[id],agent=team.spec.seats.find(row=>row.id===actor.seat),status=stageActivity(id,workflow),history=stageRecords(id,workflow,team,events),pending=history.tasks.filter(row=>row.state==='PENDING').length;return <tr key={id} aria-selected={id===stage} className={'observer-table-row '+status}><td><button aria-label={`${label} · ${actor.actor==='human'?'Bạn':actor.seat} · ${activityLabels[status]}`} aria-pressed={id===stage} onClick={()=>choose(id)}><strong>{label}</strong><small>{actor.actor==='human'?'Bạn':actor.seat}</small></button></td><td>{actor.actor==='human'?<span className="muted">Human</span>:<><span>{agent?.harness}</span><small>{agent?.model||'provider default'}</small></>}</td><td><span className={'observer-state '+status}>{activityLabels[status]}</span></td><td><span>{history.tasks.length} lượt</span><small>{pending} chờ · {history.sessions.length} phiên</small></td></tr>;})}</tbody></table></div>:<div className="observer-map-scroll" tabIndex={0} aria-label="Sơ đồ luồng nghiên cứu, có thể cuộn ngang">
        <svg className="observer-map" viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Research stage activity">
          <defs><marker id="research-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 1 L 8 5 L 0 9" fill="none" stroke="currentColor" strokeWidth="1.5"/></marker></defs>
          {positions.slice(0,-1).map((from,index)=>{const to=positions[index+1],sameRow=from.y===to.y,right=to.x>from.x;const path=sameRow?`M ${from.x+(right?nodeWidth:0)} ${from.y+nodeHeight/2} H ${to.x+(right?0:nodeWidth)}`:`M ${from.x+nodeWidth/2} ${from.y+nodeHeight} V ${to.y}`;const next=stageActivity(stages[index+1][0],workflow),prev=stageActivity(stages[index][0],workflow);return <path key={index} className={'observer-edge '+(next==='running'?'active':prev==='done'&&next==='done'?'complete':'')} d={path} markerEnd="url(#research-arrow)"/>;})}
          {stages.map(([id,label],index)=>{const actor=bindings[id],agent=team.spec.seats.find(row=>row.id===actor.seat),status=stageActivity(id,workflow),position=positions[index];return <g key={id} className={'observer-node '+status+(id===stage?' selected':'')} transform={`translate(${position.x},${position.y})`} role="button" tabIndex={0} aria-pressed={id===stage} aria-label={`${label} · ${actor.actor==='human'?'Bạn':actor.seat} · ${activityLabels[status]}`} onClick={()=>choose(id)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(id);}}}>
            <title>{label} · {actor.actor==='human'?'Bạn':`${actor.seat} · ${agent?.harness} · ${agent?.model||'provider default'}`} · {activityLabels[status]}</title>
            <rect className="observer-node-surface" width={nodeWidth} height={nodeHeight} rx="8"/>
            <circle className="observer-avatar" cx="27" cy="28" r="15"/><text className="observer-avatar-label" x="27" y="32" textAnchor="middle">{actor.actor==='human'?'U':actor.seat.slice(0,2).toUpperCase()}</text>
            <text className="observer-node-label" x="50" y="25">{shorten(label,18)}</text><text className="observer-node-actor" x="50" y="42">{shorten(actor.actor==='human'?'Bạn':actor.seat,18)}</text>
            <text className="observer-node-model" x="13" y="67">{shorten(actor.actor==='human'?'Người thực hiện':`${agent?.harness||''} · ${agent?.model||'provider default'}`,25)}</text>
            <circle className="observer-status-dot" cx="17" cy="91" r="3"/><text className="observer-node-status" x="27" y="95">{activityLabels[status]}</text>
          </g>;})}
        </svg>
      </div>}
      <div className="observer-legend"><span><i className="running"/>Đang xử lý</span><span><i className="waiting"/>Chờ bạn</span><span><i className="done"/>Đã xong</span><span><i className="idle"/>Chưa chạy</span></div>
      <p className="observer-hint">Chọn một giai đoạn để xem công việc, kết quả và phiên của agent.</p>
    </div><section className="observer-inspector" aria-label="Chi tiết agent của giai đoạn đã chọn">
      <div className="observer-inspector-head"><span className="eyebrow">{stages.find(([id])=>id===stage)?.[1]}</span><span className={'observer-state '+state}>{activityLabels[state]}</span><h3>{binding.actor==='human'?'Bạn':binding.seat}</h3><p>{binding.actor==='human'?'Bạn trực tiếp thực hiện giai đoạn này':`${seat?.harness} · ${seat?.model||'provider default'}`}</p>{binding.ask&&<small>Kết quả cần bạn duyệt trước khi tiếp tục.</small>}</div>
      <div className="observer-tabs" role="tablist" aria-label="Thông tin agent">{([['activity','Hoạt động'],['result','Kết quả'],['sessions','Phiên']] as const).map(([id,label])=><button key={id} id={'observer-tab-'+id} role="tab" aria-selected={tab===id} aria-controls={'observer-panel-'+id} onClick={()=>setTab(id)}>{label}{id==='sessions'&&records.sessions.length>0&&<span>{records.sessions.length}</span>}</button>)}</div>
      <div role="tabpanel" id={'observer-panel-'+tab} aria-labelledby={'observer-tab-'+tab} className="observer-inspector-body">
        {tab!=='sessions'&&records.tasks.length>0&&<label className="observer-turn">Lượt thực hiện<select value={task?.id||''} onChange={event=>setTaskId(event.target.value)}>{records.tasks.map((row,index)=><option key={row.id} value={row.id}>Lượt {index+1} · {sessionLabels[row.state]||row.state}</option>)}</select></label>}
        {tab==='activity'&&<>
          {binding.actor==='human'&&<p className="muted">{state==='waiting'?'Workflow đang chờ bạn trả lời tại biểu mẫu bên dưới.':'Giai đoạn này do bạn phụ trách.'}</p>}
          {records.receipts.length>0?<ol className="observer-timeline">{records.receipts.slice(-6).map((event,index)=><li key={`${event.at}-${index}`}><time>{time(event.at)}</time><span>{eventLabels[event.kind]||event.kind}</span></li>)}</ol>:<p className="muted">Chưa có hoạt động trong workflow này.</p>}
          {output.length>0&&<div className="observer-output" role="log" aria-label="Đầu ra agent của lượt đã chọn">{output.map(event=><article key={event.id}><time>{time(event.timestamp)}</time><pre>{outputText(event)}</pre></article>)}</div>}
          {output.length===0&&task&&<p className="muted">{task.state==='DONE'?'Mở Kết quả để xem phản hồi đã lưu của lượt này.':'Chưa nhận đầu ra từ lượt này.'}</p>}
        </>}
        {tab==='result'&&<>{resultText(task)?<pre className="observer-result">{resultText(task)}</pre>:<p className="muted">{binding.actor==='human'?'Kết quả được lưu khi bạn gửi biểu mẫu hoặc quyết định duyệt.':'Chưa có kết quả cho lượt này.'}</p>}{task?.result?.handoff&&<div className="observer-handoff"><strong>Bàn giao</strong><p>{task.result.handoff}</p></div>}</>}
        {tab==='sessions'&&<>{records.sessions.length===0?<p className="muted">Chưa có phiên agent cho giai đoạn này trong workflow đang chọn.</p>:records.sessions.slice().reverse().map(session=><article className="observer-session" key={session.id}><div><strong>{sessionLabels[session.state]||session.state}</strong><span>{session.provider_id}</span></div><small>{session.id.slice(0,12)}{session.created_at&&` · ${time(session.created_at)}`}</small><p>{session.stop_receipt?.tree_stopped?'Đã xác nhận dừng':session.state==='UNKNOWN'?'Cần xác minh trạng thái phiên':'Chưa có xác nhận dừng'}</p><details><summary>Chi tiết phiên và usage</summary><pre>{JSON.stringify({id:session.id,provider_session:session.provider_session,usage:session.usage,stop_receipt:session.stop_receipt},null,2)}</pre></details></article>)}</>}
      </div>
    </section></div>
  </div>;
}
