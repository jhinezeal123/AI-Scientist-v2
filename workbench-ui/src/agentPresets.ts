import {agentCall} from './agentApi';

export type Preset={id:string;name:string;harness:string;model:string|null};
import type {CustomModelDefinition} from './vendor/t3code/bridge/model';
import type {ServerProviderModel} from './vendor/t3code/bridge/contracts';
export type HarnessSpec={id:string;name?:string;kind:'native_codex'|'native_claude'|'acp'|'cli_json';models:string[];enabled?:boolean;executable?:string;args?:string[];protocol_version?:1|2;managed_home?:string|null;config_directory?:string;environment?:Record<string,string>;environment_sensitive?:string[]|null;accent_color?:string;custom_models?:CustomModelDefinition[];archived?:boolean;registry_agent_id?:string;registry_distribution?:'auto'|'binary'|'npx'|'uvx';registry_icon_url?:string;auth_method?:string;api_key?:string;gcp_project?:string;gcp_location?:string;hidden_models?:string[];favorite_models?:string[];model_order?:string[]};
export type HarnessProbe={ready:boolean;auth?:string;attention_required?:string;models?:string[];capabilities:Record<string,boolean>};
export type Harness={spec:HarnessSpec;probe:HarnessProbe|null};
export const listPresets=()=>agentCall<Preset[]>('/agent-presets');
export const listHarnesses=(details=false)=>agentCall<Harness[]>('/harnesses?probe=false'+(details?'&details=true':''));
export const saveHarness=(spec:HarnessSpec)=>agentCall<HarnessSpec>('/harnesses/'+spec.id,'PUT',spec);
export const checkHarness=(spec:HarnessSpec)=>agentCall<HarnessProbe>('/harnesses/'+spec.id+'/probe','POST',spec);
export type ModelCatalog={models:ServerProviderModel[];source:string;installed:boolean;status:'ready'|'warning'|'error';message?:string;version?:string|null;auth:'authenticated'|'unknown'|'unauthenticated';canLogout?:boolean;canAuthenticate?:boolean;documentationUrl?:string;authMethods?:{id:string;name:string;type?:string}[]};
export const discoverModels=(spec:HarnessSpec)=>agentCall<ModelCatalog>('/harnesses/'+spec.id+'/models','POST',spec);
export const savePreset=(preset:Preset)=>agentCall<Preset>('/agent-presets/'+preset.id,'PUT',preset);
export const deletePreset=(id:string)=>agentCall('/agent-presets/'+id,'DELETE');
