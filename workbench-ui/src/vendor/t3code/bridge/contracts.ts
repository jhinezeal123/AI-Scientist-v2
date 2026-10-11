/** Workbench's data boundary for the imported T3 settings components. */
export type ProviderDriverKind = string;
export const ProviderDriverKind = {make:(value:string)=>value};
export type ProviderInstanceId = string;
export type EnvironmentId = string;
export const AuthProvidersManageScope='admin';
export type AntigravityAuthMethod='oauth-personal'|'oauth-business'|'gemini-api-key'|'agent-platform';
export const ANTIGRAVITY_AUTH_METHODS=[{value:'oauth-personal' as const,label:'Google account'},{value:'oauth-business' as const,label:'Gemini Enterprise'},{value:'gemini-api-key' as const,label:'Gemini API key'},{value:'agent-platform' as const,label:'Agent Platform / Vertex AI'}];
export type ProviderAuthResponse={type:'browser';action:'accept'|'decline'}|{type:'credentials';values:Record<string,string>}|{type:'terminal';data:string;size?:{cols:number;rows:number}};
export type ProviderAuthRespondInput={instanceId:string;flowId:string;interactionId:string;response:ProviderAuthResponse};
export type AuthInteraction={type:'browser';id:string;url:string;requiresConsent?:boolean;acceptsCallback?:boolean}|{type:'terminal';id:string;output:string;outputOffset?:number}|{type:'credentials';id:string;fields:{name:string;label:string;secret?:boolean}[]}|{type:'deviceCode';id:string;url:string;userCode:string};
export type ProviderAuthState={instanceId:string;phase:string;flowId:string|null;authorizationUrl:string|null;interaction:AuthInteraction|null;expiresAt:string|null;message:string|null;methods?:{id:string;name:string;type?:string}[]};
export type ProviderInstallState={phase:string;operationId:string|null;installedVersion:string|null;version:string|null;canRemove:boolean;message:string|null;downloadedBytes:number;totalBytes:number|null};
export type AcpRegistrySearchAgent={id:string;name:string;version:string;description?:string;website?:string;repository?:string;icon?:string;distribution:'binary'|'npx'|'uvx'|null;supported:boolean};
export type AcpRegistryPrepareResult={agentId:string;version:string;distribution:AcpRegistrySearchAgent['distribution']};
export const isProviderDriverKind=(value:string):value is ProviderDriverKind=>true;
export type ProviderOptionChoice={id:string;label:string;isDefault?:boolean;description?:string};
export type ProviderOptionDescriptor =
  | {type:'select';id:string;label:string;options:ReadonlyArray<ProviderOptionChoice>;currentValue?:string;description?:string;promptInjectedValues?:ReadonlyArray<string>}
  | {type:'boolean';id:string;label:string;currentValue?:boolean;description?:string};
export type ModelCapabilities={optionDescriptors?:ReadonlyArray<ProviderOptionDescriptor>};
export type ServerProviderModel={slug:string;name:string;isCustom:boolean;isDefault?:boolean;isLegacy?:boolean;capabilities?:ModelCapabilities|null;aliases?:ReadonlyArray<string>};
export type ProviderInstanceEnvironmentVariable={name:string;value:string;sensitive:boolean;valueRedacted?:boolean};
export type ProviderInstanceConfig={driver:string;displayName?:string;accentColor?:string;enabled?:boolean;config?:Record<string,unknown>;environment?:ReadonlyArray<ProviderInstanceEnvironmentVariable>};
export const resolveProviderInstanceEnabled=(instance:ProviderInstanceConfig)=>instance.enabled!==false;
export type ServerProvider={enabled:boolean;installed:boolean;status:'ready'|'warning'|'error'|'disabled';driver?:string;displayName?:string;setup?:{canAuthenticate:boolean;canInstall:boolean;documentationUrl?:string};message?:string;version?:string|null;models:ReadonlyArray<ServerProviderModel>;auth:{status:'unknown'|'authenticated'|'unauthenticated';label?:string;type?:string;email?:string;canLogout?:boolean}};
export type ProviderSettingsFormControl='text'|'password'|'switch'|'select'|'textarea';
export type ProviderSettingsFormOption={value:string;label:string};
export type ProviderSettingsFormAnnotation={control?:ProviderSettingsFormControl;placeholder?:string;clearWhenEmpty?:'omit'|'persist';hidden?:boolean;secret?:boolean;options?:ReadonlyArray<ProviderSettingsFormOption>};
export type ProviderSettingsFormSchemaAnnotation={order?:ReadonlyArray<string>};
export type SettingsField={key:string;label:string;control:ProviderSettingsFormControl;description?:string;placeholder?:string;clearWhenEmpty:'omit'|'persist';secret?:boolean;defaultBooleanValue?:boolean;options?:ReadonlyArray<ProviderSettingsFormOption>};
export type ProviderEnvironmentField={name:string;label:string;description?:string;placeholder?:string;sensitive?:boolean};
export type ProviderClientDefinition={driverKind:ProviderDriverKind;label:string;badgeLabel?:string;settingsSchema:{fields:ReadonlyArray<SettingsField>};environmentFields?:ReadonlyArray<ProviderEnvironmentField>};
