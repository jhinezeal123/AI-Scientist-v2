import type {Event,Snapshot,Task} from './teamApi';

export type StageEvent={stage:string;kind:string;at:string;seat?:string;task_id?:string};
export type ActivityWorkflow={id:string;state:{stage:string;status:string;events:StageEvent[]}};
export type ActivityState='idle'|'running'|'waiting'|'done'|'paused'|'failed'|'unknown';
export const activityLabels:Record<ActivityState,string>={idle:'Chưa chạy',running:'Đang xử lý',waiting:'Chờ bạn',done:'Đã xong',paused:'Tạm dừng',failed:'Lỗi',unknown:'Cần đối soát'};

export function stageActivity(stage:string,workflow:ActivityWorkflow|null):ActivityState{
  if(!workflow)return 'idle';
  const state=workflow.state;
  if(state.stage===stage){
    if(state.status==='WAITING')return 'waiting';
    if(state.status==='RUNNING')return 'running';
    if(state.status==='PAUSED')return 'paused';
    if(state.status==='UNKNOWN')return 'unknown';
    if(['FAILED','CANCELLED'].includes(state.status))return 'failed';
  }
  const last=state.events.filter(event=>event.stage===stage).at(-1);
  if(last?.kind==='agent_completed'||last?.kind==='human_completed')return 'done';
  if(last?.kind==='agent_queued'||last?.kind==='agent_result_invalid'){
    if(state.status==='PAUSED')return 'paused';
    if(state.status==='UNKNOWN')return 'unknown';
    if(['FAILED','CANCELLED'].includes(state.status))return 'failed';
    return 'running';
  }
  return 'idle';
}

// A seat may serve several stages and workflows. Identity comes from workflow
// receipts, never from the seat name or a timestamp guess.
export function stageRecords(stage:string,workflow:ActivityWorkflow|null,team:Snapshot,events:Event[]){
  const receipts=workflow?.state.events.filter(event=>event.stage===stage)||[];
  const ids=[...new Set(receipts.flatMap(event=>event.task_id?[event.task_id]:[]))];
  const byId=new Map(team.tasks.map(task=>[task.id,task]));
  const tasks=ids.flatMap(id=>byId.has(id)?[byId.get(id)!]:[]);
  const taskIds=new Set(ids);
  const resultSessionIds=new Set(tasks.flatMap(task=>task.result?.session_id?[task.result.session_id]:[]));
  const sessions=team.sessions.filter(session=>session.task_id?taskIds.has(session.task_id):resultSessionIds.has(session.id));
  const sessionIds=new Set(sessions.map(session=>session.id));
  const output=events.filter(event=>event.task_id?taskIds.has(event.task_id):Boolean(event.session_id&&sessionIds.has(event.session_id)));
  return {receipts,tasks,sessions,output};
}

export function resultText(task:Task|undefined):string{
  if(!task?.result)return '';
  if(task.result.error)return task.result.error;
  const text=task.result.summary||'';
  try{
    const value=JSON.parse(text);
    if(value?.action==='finish'&&typeof value.result?.summary==='string')return value.result.summary;
    if(typeof value?.response==='string')return value.response;
    return JSON.stringify(value,null,2);
  }catch{return text;}
}

export function outputText(event:Event):string{
  if(typeof event.data.text!=='string')return '';
  const text=event.data.text;
  try{
    const value=JSON.parse(text);
    if(value.item?.type==='agent_message'&&typeof value.item.text==='string'){
      try{const message=JSON.parse(value.item.text);return typeof message.summary==='string'?resultText({result:{summary:message.summary}} as Task):value.item.text;}catch{return value.item.text;}
    }
    if(value.item?.type==='error'&&typeof value.item.message==='string')return value.item.message;
    if(value.type&&['thread.started','turn.started','turn.completed'].includes(value.type))return '';
    return text;
  }catch{return text;}
}
