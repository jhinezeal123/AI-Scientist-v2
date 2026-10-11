/** Map Workbench persistence to T3's configuration UI contracts. No other feature state. */
import type {HarnessSpec,ModelCatalog} from './agentPresets';
import type {ProviderClientDefinition,ProviderInstanceConfig,ServerProvider} from './vendor/t3code/bridge/contracts';
import {readCustomModelEntries} from './vendor/t3code/bridge/model';

export const providerDefinitions:ProviderClientDefinition[]=[
  {driverKind:'antigravity',label:'Antigravity',settingsSchema:{fields:[
    {key:'binaryPath',label:'Binary path',control:'text',clearWhenEmpty:'omit',placeholder:'Managed runtime',description:'Leave blank to use the official Antigravity ACP runtime.'},
    {key:'authMethod',label:'Sign-in method',control:'select',clearWhenEmpty:'omit',options:[{value:'oauth-personal',label:'Google account'},{value:'oauth-business',label:'Gemini Enterprise'},{value:'gemini-api-key',label:'Gemini API key'},{value:'agent-platform',label:'Agent Platform / Vertex AI'}]},
    {key:'apiKey',label:'API key',control:'password',secret:true,clearWhenEmpty:'persist',placeholder:'For API key sign-in methods'},
    {key:'gcpProject',label:'GCP project',control:'text',clearWhenEmpty:'omit',placeholder:'For Enterprise or Vertex AI'},
    {key:'gcpLocation',label:'GCP location',control:'text',clearWhenEmpty:'omit',placeholder:'For Enterprise or Vertex AI'}]}},
  {driverKind:'codex',label:'Codex',settingsSchema:{fields:[
    {key:'binaryPath',label:'Binary path',control:'text',clearWhenEmpty:'omit',placeholder:'codex',description:'Path to the Codex executable on this machine.'},
    {key:'homePath',label:'Config directory',control:'text',clearWhenEmpty:'omit',placeholder:'~/.codex',description:'Use a separate configuration directory for another account or provider.'}]}},
  {driverKind:'claudeAgent',label:'Claude Code',settingsSchema:{fields:[
    {key:'binaryPath',label:'Binary path',control:'text',clearWhenEmpty:'omit',placeholder:'claude'},
    {key:'homePath',label:'Config directory',control:'text',clearWhenEmpty:'omit',placeholder:'~/.claude'}]}},
  {driverKind:'acpRegistry',label:'ACP Registry',settingsSchema:{fields:[
    {key:'agentId',label:'Agent',control:'text',clearWhenEmpty:'persist',description:'Agent ID from the official ACP Registry.'},
    {key:'commandPath',label:'Executable override',control:'text',clearWhenEmpty:'omit',placeholder:'Managed runtime'},
    {key:'authMethodId',label:'Authentication method',control:'text',clearWhenEmpty:'omit',placeholder:'Provider default'}]}},
  {driverKind:'localAcp',label:'Local ACP',settingsSchema:{fields:[
    {key:'commandPath',label:'Executable',control:'text',clearWhenEmpty:'persist',placeholder:'Agent executable or native entrypoint'},
    {key:'protocolVersion',label:'Protocol version',control:'select',clearWhenEmpty:'omit',options:[{value:'1',label:'ACP v1'},{value:'2',label:'ACP v2'}]}]}},
  {driverKind:'cliJson',label:'CLI JSON',settingsSchema:{fields:[
    {key:'commandPath',label:'Executable',control:'text',clearWhenEmpty:'persist',placeholder:'Workbench CLI JSON executable'}]}},
];
const kinds={native_codex:'codex',native_claude:'claudeAgent',acp:'localAcp',cli_json:'cliJson'} as const;
export const driverFor=(spec:HarnessSpec)=>spec.registry_agent_id==='antigravity-acp'?'antigravity':spec.registry_agent_id?'acpRegistry':kinds[spec.kind];
export const definitionFor=(spec:HarnessSpec)=>providerDefinitions.find(d=>d.driverKind===driverFor(spec))!;
const secret='__WORKBENCH_STORED_SECRET__';
export function instanceFor(spec:HarnessSpec):ProviderInstanceConfig{
  const environment=Object.entries(spec.environment??{}).map(([name,value])=>({name,value:value===secret?'':value,sensitive:spec.environment_sensitive===null||spec.environment_sensitive===undefined||spec.environment_sensitive.includes(name),valueRedacted:value===secret}));
  return {driver:driverFor(spec),displayName:spec.name||definitionFor(spec).label,enabled:spec.enabled!==false,accentColor:spec.accent_color||undefined,environment,
    config:{source:spec.registry_agent_id?'registry':'local',agentId:spec.registry_agent_id??'',registryIconUrl:spec.registry_icon_url??'',binaryPath:spec.executable??'',commandPath:spec.executable??'',commandArgs:spec.args??[],protocolVersion:String(spec.protocol_version??1),customModels:spec.custom_models??[],homePath:spec.config_directory??'',authMethod:spec.auth_method||'oauth-personal',authMethodId:spec.auth_method??'',apiKey:spec.api_key??'',gcpProject:spec.gcp_project??'',gcpLocation:spec.gcp_location??'',hiddenModels:spec.hidden_models??[],favoriteModels:spec.favorite_models??[],modelOrder:spec.model_order??[]}};
}
export function specFromInstance(previous:HarnessSpec,instance:ProviderInstanceConfig):HarnessSpec{
  const config=instance.config??{},environment:Record<string,string>={},sensitive:string[]=[];
  for(const variable of instance.environment??[]){
    if(Object.hasOwn(environment,variable.name))throw new Error('Environment variable names must be unique.');
    environment[variable.name]=variable.valueRedacted||(previous.environment?.[variable.name]===secret&&variable.value==='')?secret:variable.value;
    if(variable.sensitive)sensitive.push(variable.name);
  }
  const antigravity=instance.driver==='antigravity';
  const command=previous.kind.startsWith('native_')||antigravity?config.binaryPath:config.commandPath;
  return {...previous,name:instance.displayName??'',enabled:instance.enabled!==false,accent_color:instance.accentColor??'',executable:String(command??''),args:previous.kind.startsWith('native_')?[]:(config.commandArgs as string[]??[]),protocol_version:config.protocolVersion==='2'?2:1,
    config_directory:String(config.homePath??'').trim(),environment,environment_sensitive:sensitive,custom_models:readCustomModelEntries(config.customModels),registry_agent_id:antigravity?'antigravity-acp':instance.driver==='acpRegistry'?String(config.agentId??''):'',registry_icon_url:String(config.registryIconUrl??''),auth_method:String(antigravity?config.authMethod??'oauth-personal':config.authMethodId??''),api_key:String(config.apiKey??''),gcp_project:String(config.gcpProject??''),gcp_location:String(config.gcpLocation??''),hidden_models:config.hiddenModels as string[]??[],favorite_models:config.favoriteModels as string[]??[],model_order:config.modelOrder as string[]??[]};
}
export function providerFromCatalog(spec:HarnessSpec,catalog?:ModelCatalog):ServerProvider{
  return {driver:driverFor(spec),displayName:spec.name||definitionFor(spec).label,enabled:spec.enabled!==false,installed:catalog?.installed??false,status:spec.enabled===false?'disabled':catalog?.status??'warning',message:catalog?.message??(!catalog?'Refresh to read models and provider status.':undefined),version:catalog?.version,models:catalog?.models??[],auth:{status:catalog?.auth??'unknown',canLogout:spec.registry_agent_id==='antigravity-acp'||catalog?.canLogout},setup:spec.kind==='acp'?{canInstall:!!spec.registry_agent_id,canAuthenticate:catalog?.canAuthenticate??true,documentationUrl:catalog?.documentationUrl}:undefined};
}
export function connectionKey(spec:HarnessSpec){return JSON.stringify([spec.kind,spec.executable,spec.args,spec.managed_home,spec.config_directory,spec.protocol_version,spec.environment,spec.registry_agent_id,spec.auth_method,spec.api_key,spec.gcp_project,spec.gcp_location]);}
