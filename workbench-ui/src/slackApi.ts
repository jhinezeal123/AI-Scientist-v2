import {agentCall} from './agentApi';

export type SlackConfig={enabled:boolean;channel:string|null};
export const readSlack=()=>agentCall<SlackConfig>('/integrations/slack');
export const saveSlack=(config:SlackConfig)=>agentCall<SlackConfig>('/integrations/slack','PUT',config);
export const sendSlack=(text:string)=>agentCall('/integrations/slack/messages','POST',{text});
