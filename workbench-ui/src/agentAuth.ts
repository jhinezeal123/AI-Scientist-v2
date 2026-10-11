import {agentCall} from './agentApi';

export type Identity={id:string;scopes:string[];rig_ids:string[];csrf?:string};
export async function readIdentity(){
  const identity=await agentCall<Identity>('/identity');
  if(identity.csrf)sessionStorage.setItem('agent-csrf',identity.csrf);
  return identity;
}
