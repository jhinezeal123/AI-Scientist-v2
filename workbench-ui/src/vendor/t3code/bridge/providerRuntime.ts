/** Bind T3's setup components to Workbench's human administrative API. */
import {useEffect,useRef,useState} from 'react';
import {agentCall} from '../../../agentApi';
import type {AcpRegistryPrepareResult,AcpRegistrySearchAgent,ProviderAuthState,ProviderInstallState,ProviderInstanceConfig} from './contracts';

type Target={environmentId?:string;input:{instanceId?:string;agentId?:string;[key:string]:unknown}};
type Query<T>={key:string;load:()=>Promise<T>};
export type AtomCommandResult<A,E>={_tag:'Success';value:A}|{_tag:'Failure';error:E};
export const isAtomCommandInterrupted=(_result?:unknown)=>false;
export const squashAtomCommandFailure=(result:unknown)=>result&&typeof result==='object'&&'error' in result?(result as {error:unknown}).error:result;
export const readEnvironmentScope=(_environment?:string,_scope?:string)=>true;
export const useEnvironmentScope=(_environment:string,_scope:string)=>true;
export const isConfiguredAcpRegistryAgent=(instances:Readonly<Record<string,ProviderInstanceConfig>>,id:string)=>Object.values(instances).some(instance=>instance.config?.agentId===id);
export const writeTextToClipboard=(value:string,_label?:string)=>navigator.clipboard.writeText(value);
export const ensureLocalApi=()=>({shell:{openExternal:async(url:string)=>{if(!/^https?:\/\//i.test(url))throw new Error('Invalid sign-in link');window.open(url,'_blank','noopener,noreferrer');}},dialogs:{confirm:async(message:string)=>window.confirm(message)}});
const changed=(id?:string)=>window.dispatchEvent(new CustomEvent('workbench:provider-changed',{detail:{id}}));
function provider(target:Target,suffix:string,method='GET'){
  const {instanceId,...body}=target.input;
  return agentCall<unknown>('/harnesses/'+encodeURIComponent(String(instanceId))+suffix,method,method==='GET'?undefined:body);
}
function command(suffix:string,method='POST'){return async(target:Target)=>{const value=await provider(target,suffix,method);changed(target.input.instanceId);if(suffix==='/auth/logout'||method==='DELETE')window.dispatchEvent(new CustomEvent('workbench:provider-ready',{detail:{id:target.input.instanceId}}));return value;};}
export const serverEnvironment={
  providerAuthState:(target:Target):Query<ProviderAuthState>=>({key:'auth:'+target.input.instanceId,load:()=>provider(target,'/auth') as Promise<ProviderAuthState>}),
  providerInstallState:(target:Target):Query<ProviderInstallState>=>({key:'install:'+target.input.instanceId,load:async()=>{const value=await provider(target,'/installation') as Record<string,unknown>;return {...value,installedVersion:value.installedVersion??(value.phase==='succeeded'?value.version:null),canRemove:value.phase==='succeeded',downloadedBytes:value.downloadedBytes??0,totalBytes:value.totalBytes??null} as ProviderInstallState;}}),
  startProviderAuth:command('/auth/start'),respondProviderAuth:command('/auth/respond'),completeProviderAuth:command('/auth/complete'),cancelProviderAuth:command('/auth/cancel'),logoutProviderAuth:command('/auth/logout'),
  startProviderInstall:command('/install'),cancelProviderInstall:command('/installation/cancel'),removeProviderInstallation:command('/installation','DELETE'),
  searchAcpRegistry:({input}:{environmentId?:string;input:{query:string}}):Query<{agents:AcpRegistrySearchAgent[]}>=>({key:'registry:'+input.query,load:()=>agentCall('/acp-registry?query='+encodeURIComponent(input.query))}),
  cancelAcpRegistryPreparation:async({input}:{environmentId?:string;input:{agentId:string}})=>{
    const path='/acp-registry/'+encodeURIComponent(input.agentId)+'/installation';
    const state=await agentCall<{operationId:string}>(path);
    return agentCall(path+'/cancel','POST',{operationId:state.operationId});
  },
  prepareAcpRegistryAgent:async({input}:{environmentId?:string;input:{agentId:string}}):Promise<AcpRegistryPrepareResult>=>{
    let state=await agentCall<{phase:string;message?:string}>('/acp-registry/'+encodeURIComponent(input.agentId)+'/prepare','POST',{});
    while(!['succeeded','failed','cancelled'].includes(state.phase)){await new Promise(resolve=>setTimeout(resolve,1500));state=await agentCall('/acp-registry/'+encodeURIComponent(input.agentId)+'/installation');}
    if(state.phase!=='succeeded')throw new Error(state.message||'Could not prepare this ACP agent.');
    const result=await agentCall<{agents:AcpRegistrySearchAgent[]}>('/acp-registry?query='+encodeURIComponent(input.agentId));
    const agent=result.agents.find(row=>row.id===input.agentId)!;
    return {agentId:agent.id,version:agent.version,distribution:agent.distribution};
  },
};
export function useAtomCommand<A,T>(_command:(target:T)=>Promise<A>,_options?:unknown){return async(target:T):Promise<AtomCommandResult<A,Error>>=>{try{return {_tag:'Success',value:await _command(target)};}catch(reason){return {_tag:'Failure',error:reason instanceof Error?reason:new Error(String(reason))};}};}
export function useEnvironmentQuery<T>(query:Query<T>){
  const [data,setData]=useState<T|null>(null),[error,setError]=useState<string|null>(null),[pending,setPending]=useState(true),[revision,setRevision]=useState(0);
  const latest=useRef(query);latest.current=query;
  const previousPhase=useRef<string|undefined>(undefined);
  const refresh=()=>setRevision(n=>n+1);
  useEffect(()=>{let cancelled=false;let running=false;let timer:ReturnType<typeof setTimeout>|undefined;
    previousPhase.current=undefined;setData(null);setError(null);setPending(true);
    async function load(){
      if(running||cancelled)return;running=true;if(timer)clearTimeout(timer);
      try{const value=await latest.current.load();if(cancelled)return;setData(value);setError(null);setPending(false);
        const phase=(value as {phase?:string}).phase;
        if(phase==='succeeded'&&previousPhase.current&&previousPhase.current!=='succeeded')window.dispatchEvent(new CustomEvent('workbench:provider-ready',{detail:{id:query.key.split(':')[1]}}));
        previousPhase.current=phase;
      }catch(reason){if(cancelled)return;setError(reason instanceof Error?reason.message:String(reason));setPending(false);}
      running=false;
      if(!cancelled&&(query.key.startsWith('auth:')||query.key.startsWith('install:')))timer=setTimeout(()=>void load(),2000);
    }
    void load();const onChange=()=>void load();window.addEventListener('workbench:provider-changed',onChange);
    return()=>{cancelled=true;if(timer)clearTimeout(timer);window.removeEventListener('workbench:provider-changed',onChange);};
  },[query.key,revision]);
  return {data,error,isPending:pending,refresh};
}
