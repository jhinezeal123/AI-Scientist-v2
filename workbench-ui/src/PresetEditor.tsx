import {useState} from 'react';
import {Harness,Preset,ModelCatalog,savePreset} from './agentPresets';
import {instanceFor} from './T3ProviderSetup';
import {providerModelOptions,ModelPreferences} from './providerModelOptions';
import {SettingsSection,SettingsRow} from './vendor/t3code/components/settings/settingsLayout';
import {Input} from './vendor/t3code/components/ui/input';
import {Button} from './vendor/t3code/components/ui/button';
import {Select,SelectTrigger,SelectValue,SelectPopup,SelectItem} from './vendor/t3code/components/ui/select';
import useAgentAction from './useAgentAction';

export default function PresetEditor({initial,harnesses,catalogs,preferences,onProviderSelected,onSaved,onCancel,onConfigure}:{initial:Preset;harnesses:Harness[];catalogs:Record<string,ModelCatalog>;preferences:Record<string,ModelPreferences>;onProviderSelected:(id:string)=>void;onSaved:(preset:Preset)=>void;onCancel:()=>void;onConfigure:(id:string)=>void}){
  const [draft,setDraft]=useState(initial),{busy,error,action}=useAgentAction();
  const agent=harnesses.find(h=>h.spec.id===draft.harness),label=agent?instanceFor(agent.spec).displayName:draft.harness;
  const models=agent?providerModelOptions(agent.spec,catalogs[draft.harness],preferences[draft.harness],draft.model):[];
  const known=models.some(m=>m.slug===draft.model),modelName=models.find(m=>m.slug===draft.model)?.name||draft.model||'Agent default';
  return <SettingsSection title="Agent + model preset" headerAction={<Button size="xs" variant="ghost-muted" onClick={onCancel}>Cancel</Button>}>
    {error&&<p role="alert" className="px-4 py-3 text-sm text-destructive">{error}</p>}
    <SettingsRow title="Provider" control={<Select value={draft.harness} onValueChange={value=>{if(value){setDraft({...draft,harness:value,model:null});onProviderSelected(value);}}}><SelectTrigger aria-label="Preset provider" size="sm" className="w-full @min-[32rem]/settings-row:w-56"><SelectValue>{label}</SelectValue></SelectTrigger><SelectPopup>{harnesses.filter(h=>h.spec.enabled!==false).map(h=><SelectItem key={h.spec.id} value={h.spec.id}>{instanceFor(h.spec).displayName}</SelectItem>)}</SelectPopup></Select>}/>
    <SettingsRow title="Model" description={<Button size="xs" variant="ghost-muted" onClick={()=>onConfigure(draft.harness)}>Manage this provider's models</Button>} control={<Select value={draft.model??'__default__'} onValueChange={value=>setDraft({...draft,model:value==='__default__'?null:value})}><SelectTrigger size="sm" aria-label="Preset model" className="w-full @min-[32rem]/settings-row:w-56"><SelectValue>{modelName}</SelectValue></SelectTrigger><SelectPopup><SelectItem value="__default__">Agent default</SelectItem>{draft.model&&!known&&<SelectItem value={draft.model} disabled>{draft.model} (saved, unavailable)</SelectItem>}{models.map(m=><SelectItem key={m.slug} value={m.slug}>{m.name}{m.isCustom?' · Custom':''}</SelectItem>)}</SelectPopup></Select>}/>
    <SettingsRow title={<label htmlFor="preset-name">Display name</label>} description="Optional. The provider and model are used if left empty." control={<Input id="preset-name" size="sm" className="@min-[32rem]/settings-row:w-56" maxLength={120} value={draft.name} placeholder={`${label} / ${modelName}`} onChange={event=>setDraft({...draft,name:event.target.value})}/>}/>
    <div className="flex justify-end gap-2 px-4 py-3"><Button size="sm" disabled={busy||!agent||agent.spec.enabled===false} onClick={()=>void action(async()=>onSaved(await savePreset({...draft,name:(draft.name.trim()||`${label} / ${modelName}`).slice(0,120)})))}>{busy?'Saving…':'Save preset'}</Button></div>
  </SettingsSection>;
}
