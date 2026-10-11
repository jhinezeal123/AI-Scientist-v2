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

export const agentCall=<T,>(path:string,method='GET',body?:unknown)=>teamApi<T>(path,'',method,body);
