import {agentCall} from './agentApi';

export type Device={id:string;name:string;revoked:boolean;expires_at:string;scopes:string[];rig_ids:string[]};
export type ProjectReference={id:string;name:string};
export type Pairing={pairing_id:string;code:string;expires_at:string};
export const listDevices=()=>agentCall<Device[]>('/devices');
export const revokeDevice=(id:string)=>agentCall('/devices/'+id,'DELETE');
export const exchangePair=(pairing_id:string,code:string,name:string)=>agentCall('/pair/exchange','POST',{pairing_id,code,name});
export const pairProject=(projectId:string,research:boolean)=>agentCall<Pairing>('/pair','POST',{
  rig_ids:[projectId],scopes:['read',...(research?['research']:[])],
});
export async function readRemoteSettings(loadProjects:()=>Promise<ProjectReference[]>,admin:boolean){
  const [projects,devices]=await Promise.allSettled([loadProjects(),admin?listDevices():Promise.resolve([])]);
  return {projects,devices};
}
