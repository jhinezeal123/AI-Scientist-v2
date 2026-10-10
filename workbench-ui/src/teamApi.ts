export type Policy={sandbox:'read-only';file_edits:boolean;terminal:boolean;network:boolean;allowed_paths:string[];max_files:number;max_file_bytes:number};
export type Seat={id:string;role:string;pod:string;harness:string;model:string|null;instructions:string;policy:Policy};
export type RigSpec={version:2;name:string;project_id:string|null;base_ref:string;pods:{id:string;max_parallel:number}[];seats:Seat[];context:unknown[];max_parallel:number;timeout_seconds:number;template:string|null};
export type Team={id:string;spec:RigSpec;enabled:boolean;revision:number};
export type Task={id:string;seat:string;request_id:string;state:string;depends_on:string|null;payload:{instruction?:string;argv?:string[]};result:{summary?:string;error?:string;checks?:string[];handoff?:string;checkpoint?:string;session_id?:string}|null};
export type Session={id:string;seat_id:string;task_id?:string|null;created_at?:string;updated_at?:string;state:string;provider_id:string;provider_session:string|null;usage:Record<string,unknown>;stop_receipt:Record<string,unknown>|null};
export type Snapshot=Team&{tasks:Task[];seats:{id:string;state:string;worktree:string|null;checkpoint:string|null}[];sessions:Session[]};
export type Harness={spec:{id:string;kind:string;models:string[]};probe:{ready:boolean;auth?:string;attention_required?:string;capabilities:Record<string,boolean>}};
export type Event={id:number;kind:string;seat_id:string|null;task_id?:string|null;session_id?:string|null;request_id?:string|null;provider_id?:string|null;timestamp:string;data:Record<string,unknown>};
export type Permission={id:string;session_id:string;operation:{options?:{optionId:string;name:string;kind:string}[];toolCall?:unknown;subject?:unknown}};
export type Device={id:string;name:string;revoked:boolean;expires_at:string;scopes:string[];rig_ids:string[]};
// Preserve an intent across lost responses, reloads and reconnects. Store only
// its digest and random ID; prompts and credentials stay out of browser storage.
export async function teamIntent(key:string,body:unknown):Promise<{id:string;ack:()=>void}>{
  const bytes=new TextEncoder().encode(JSON.stringify(body));
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
  const storageKey='agent-intent:'+key+':'+hash;
  const id=sessionStorage.getItem(storageKey)||crypto.randomUUID();
  sessionStorage.setItem(storageKey,id);
  return {id,ack:()=>sessionStorage.removeItem(storageKey)};
}
export async function teamApi<T>(path:string,token='',method='GET',body?:unknown):Promise<T>{
  const csrf=sessionStorage.getItem('agent-csrf');
  const response=await fetch('/api/agent-management'+path,{method,credentials:'same-origin',headers:{
    ...(token?{Authorization:'Bearer '+token}:{}),...(csrf?{'X-Agent-CSRF':csrf}:{}),...(body!==undefined?{'Content-Type':'application/json'}:{})},
    ...(body!==undefined?{body:JSON.stringify(body)}:{})});
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
  return result as T;
}
