import {useState} from 'react';
import {RadioGroup} from '@base-ui/react/radio-group';
import {Radio} from '@base-ui/react/radio';
import {HarnessSpec,saveHarness} from './agentPresets';
import {providerDefinitions,specFromInstance} from './T3ProviderSetup';
import type {ProviderInstanceConfig} from './vendor/t3code/bridge/contracts';
import {Dialog} from './vendor/t3code/components/ui/dialog';
import {WizardPopup,WizardHeader,WizardSteps,WizardPanel,WizardFooter} from './vendor/t3code/components/ui/wizard';
import {SettingsGroup} from './vendor/t3code/components/settings/SettingsGroup';
import {SettingsRow} from './vendor/t3code/components/settings/settingsLayout';
import {ProviderSettingsForm} from './vendor/t3code/components/settings/ProviderSettingsForm';
import {ProviderEnvironmentSection} from './vendor/t3code/components/settings/ProviderInstanceCard';
import {ProviderAccentColorPicker} from './vendor/t3code/components/settings/ProviderAccentColorPicker';
import {ProviderInstanceIcon} from './vendor/t3code/components/chat/ProviderInstanceIcon';
import {Button} from './vendor/t3code/components/ui/button';
import {Input} from './vendor/t3code/components/ui/input';
import useAgentAction from './useAgentAction';
import {AcpRegistrySearchStep} from './vendor/t3code/components/settings/AcpRegistrySearchStep';
import type {AcpRegistrySearchAgent} from './vendor/t3code/bridge/contracts';

/** T3's Provider → Identity → Config wizard bound to the Workbench API. */
export default function T3AddProviderDialog({onAdded,onClose,initialDriver='codex'}:{onAdded:(spec:HarnessSpec)=>void;onClose:()=>void;initialDriver?:'codex'|'acpRegistry'}){
  const [step,setStep]=useState(0),[driver,setDriver]=useState<string>(initialDriver),[idOverride,setIdOverride]=useState<string|null>(null);
  const [showProviderChoices,setShowProviderChoices]=useState(initialDriver!=='acpRegistry');
  const [suffix]=useState(()=>crypto.randomUUID().slice(0,8));
  const [drafts,setDrafts]=useState<Record<string,ProviderInstanceConfig>>({});
  const [registryAgent,setRegistryAgent]=useState<AcpRegistrySearchAgent|null>(null),[preparing,setPreparing]=useState(false);
  const definition=providerDefinitions.find(d=>d.driverKind===driver)!;
  const instance=drafts[driver]??{driver,displayName:'',enabled:true,config:{},environment:[]};
  const label=instance.displayName?.trim()||definition.label;
  const id=idOverride??(driver+'_'+label.toLowerCase().replace(/[^a-z0-9]+/g,'_').slice(0,30)+'_'+suffix);
  const {busy,error,action}=useAgentAction();
  const idError=!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(id)?"Letters, digits, '-' or '_', up to 64 characters.":null;
  function update(next:Partial<ProviderInstanceConfig>){setDrafts(current=>({...current,[driver]:{...instance,...next}}));}
  const kind:HarnessSpec['kind']=driver==='codex'?'native_codex':driver==='claudeAgent'?'native_claude':['acpRegistry','localAcp','antigravity'].includes(driver)?'acp':'cli_json';
  function prepared(agent:AcpRegistrySearchAgent){setRegistryAgent(agent);setDrafts(rows=>({...rows,acpRegistry:{driver:'acpRegistry',displayName:agent.name,enabled:true,config:{agentId:agent.id,registryIconUrl:agent.icon??''}}}));setStep(1);}
  return <Dialog open onOpenChange={open=>!open&&!busy&&!preparing&&onClose()}><WizardPopup size="wide" showCloseButton={!busy&&!preparing}>
    <WizardHeader title="Add provider" description="Add a separate provider instance with its own configuration.">
      <WizardSteps steps={['Provider','Identity','Config']} currentStep={step} summaries={[definition.label,label]} onStepChange={value=>!busy&&!preparing&&(!idError||value<2)&&setStep(value)}/>
    </WizardHeader>
    <WizardPanel>
      {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
      {step===0&&<div className="grid gap-3">{showProviderChoices?<><div id="add-instance-driver-label" className="text-sm font-medium text-foreground">Provider</div><RadioGroup value={driver} onValueChange={value=>{setDriver(value);setIdOverride(null);if(value==='acpRegistry')setShowProviderChoices(false);}} aria-labelledby="add-instance-driver-label" disabled={preparing} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {providerDefinitions.map(option=><Radio.Root key={option.driverKind} value={option.driverKind} className="relative flex cursor-pointer items-center gap-3 rounded-lg bg-card px-3 py-3 text-left text-muted-foreground outline-none ring-1 ring-black/5 hover:bg-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring data-checked:bg-primary/8 data-checked:text-foreground data-checked:ring-2 data-checked:ring-inset data-checked:ring-primary dark:bg-white/3 dark:ring-white/5 dark:hover:bg-white/5 dark:data-checked:bg-primary/15 dark:data-checked:ring-primary"><ProviderInstanceIcon driverKind={option.driverKind} displayName={option.label} iconClassName="size-4"/><span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{option.label}</span></Radio.Root>)}
      </RadioGroup></>:<div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">ACP Registry</span><Button variant="ghost-muted" size="xs" disabled={preparing} onClick={()=>setShowProviderChoices(true)}>Change provider</Button></div>}{driver==='acpRegistry'&&<AcpRegistrySearchStep environmentId="local" providerInstances={{}} onPrepared={prepared} onManualConfiguration={()=>{setRegistryAgent(null);setStep(1);}} onLocalConfiguration={()=>{setDriver('localAcp');setShowProviderChoices(true);}} onPreparingChange={setPreparing}/>}</div>}
      {step===1&&<SettingsGroup variant="plain">
        <SettingsRow title={<label htmlFor="add-provider-name">Display name</label>} control={<Input id="add-provider-name" size="sm" className="@min-[32rem]/settings-row:w-56" value={instance.displayName??''} placeholder={definition.label+' Work'} maxLength={120} onChange={event=>update({displayName:event.target.value})}/>}/>
        <SettingsRow title={<label htmlFor="add-provider-instance-id">Instance ID</label>} description={idError??"Letters, digits, '-' or '_'."} control={<Input id="add-provider-instance-id" size="sm" className="@min-[32rem]/settings-row:w-56" value={id} aria-invalid={!!idError} onChange={event=>setIdOverride(event.target.value)}/>}/>
        <SettingsRow title="Accent color" control={<ProviderAccentColorPicker displayName={label} value={instance.accentColor} onCommit={value=>update({accentColor:value})} layout="inline"/>}/>
      </SettingsGroup>}
      {step===2&&<div className="space-y-4"><SettingsGroup variant="plain"><ProviderSettingsForm definition={definition} value={instance.config} idPrefix="add-provider" variant="settings" onChange={config=>update({config})}/></SettingsGroup><SettingsGroup variant="plain"><ProviderEnvironmentSection environment={instance.environment??[]} onChange={environment=>update({environment})}/></SettingsGroup></div>}
    </WizardPanel>
    <WizardFooter><Button variant={step===0?'ghost-muted':'outline'} size="sm" disabled={busy||preparing} onClick={()=>step===0?onClose():setStep(step-1)}>{step===0?'Cancel':'Back'}</Button><Button size="sm" disabled={busy||preparing||!!idError||(step===0&&driver==='acpRegistry'&&!registryAgent)} onClick={()=>step<2?setStep(step+1):void action(async()=>onAdded(await saveHarness(specFromInstance({id,kind,models:[],environment:{}},instance))))}>{busy?'Adding…':step<2?'Continue':'Add provider'}</Button></WizardFooter>
  </WizardPopup></Dialog>;
}
