import {useEffect,useRef,useState} from 'react';
import {PlusIcon,RefreshCwIcon,CopyIcon,PencilIcon,Trash2Icon} from 'lucide-react';
import {Preset,Harness,HarnessSpec,ModelCatalog,listPresets,listHarnesses,saveHarness,deletePreset,discoverModels} from './agentPresets';
import {connectionKey,definitionFor,instanceFor,providerFromCatalog,specFromInstance} from './T3ProviderSetup';
import type {ProviderInstanceConfig} from './vendor/t3code/bridge/contracts';
import {ProviderInstanceCard} from './vendor/t3code/components/settings/ProviderInstanceCard';
import {SettingsGroup} from './vendor/t3code/components/settings/SettingsGroup';
import {SettingsSection,SettingsRow} from './vendor/t3code/components/settings/settingsLayout';
import {ScrollArea} from './vendor/t3code/components/ui/scroll-area';
import {Button} from './vendor/t3code/components/ui/button';
import {TooltipProvider} from './vendor/t3code/components/ui/tooltip';
import {ProviderSetupSection} from './vendor/t3code/components/settings/ProviderSetupSection';
import T3AddProviderDialog from './T3AddProviderDialog';
import PresetEditor from './PresetEditor';

import {ModelPreferences as Preferences,emptyModelPreferences as emptyPreferences} from './providerModelOptions';
function readPreferences():Record<string,Preferences>{try{return JSON.parse(localStorage.getItem('workbench.provider-model-preferences')||'{}');}catch{return {};}}

export default function PresetSettings({admin}:{admin:boolean}){
  const [harnesses,setHarnesses]=useState<Harness[]>([]),[presets,setPresets]=useState<Preset[]>([]),[catalogs,setCatalogs]=useState<Record<string,ModelCatalog>>({});
  const [selected,setSelected]=useState(''),[adding,setAdding]=useState<'codex'|'acpRegistry'|null>(null),[draft,setDraft]=useState<Preset|null>(null);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[checking,setChecking]=useState<Record<string,boolean>>({}),[pending,setPending]=useState(0);
  const [preferences,setPreferences]=useState(readPreferences);
  const queue=useRef(Promise.resolve()),versions=useRef<Record<string,number>>({}),checks=useRef<Record<string,number>>({});
  const mounted=useRef(true),current=useRef(harnesses);current.current=harnesses;
  useEffect(()=>{mounted.current=true;let cancelled=false;Promise.all([listHarnesses(admin),listPresets()]).then(([providers,pairs])=>{if(cancelled)return;setHarnesses(providers);setPresets(pairs);setSelected(providers[0]?.spec.id||'');setLoading(false);}).catch(reason=>{if(!cancelled){setError(String(reason.message||reason));setLoading(false);}});return()=>{cancelled=true;mounted.current=false;};},[admin]);
  useEffect(()=>{setPreferences(previous=>{const next={...previous};for(const row of harnesses){const spec=row.spec;next[spec.id]={hidden:spec.hidden_models??[],favorites:spec.favorite_models??[],order:spec.model_order??[]};}return next;});},[harnesses]);
  function preference(id:string,patch:Partial<Preferences>){const prefs={...(preferences[id]??emptyPreferences),...patch};setPreferences(rows=>{const next={...rows,[id]:prefs};localStorage.setItem('workbench.provider-model-preferences',JSON.stringify(next));return next;});const spec=current.current.find(row=>row.spec.id===id)?.spec;if(spec){const instance=instanceFor(spec);update(id,{...instance,config:{...instance.config,hiddenModels:prefs.hidden,favoriteModels:prefs.favorites,modelOrder:prefs.order}});}}
  function update(id:string,instance:ProviderInstanceConfig){
    const previous=current.current.find(h=>h.spec.id===id)?.spec;if(!previous)return;
    let spec:HarnessSpec;try{spec=specFromInstance(previous,instance);}catch(reason){setError(String((reason as Error).message));return;}
    const revision=(versions.current[id]??0)+1;versions.current[id]=revision;
    setError('');setNotice('');setPending(n=>n+1);
    const apply=(rows:Harness[])=>rows.map(row=>row.spec.id===id?{...row,spec}:row);
    current.current=apply(current.current);setHarnesses(apply);
    queue.current=queue.current.catch(()=>{}).then(async()=>{
      try{const saved=await saveHarness(spec);if(mounted.current&&versions.current[id]===revision){const replace=(rows:Harness[])=>rows.map(row=>row.spec.id===id?{...row,spec:saved}:row);current.current=replace(current.current);setHarnesses(replace);setNotice('Saved');}}
      catch(reason){if(mounted.current)setError(String((reason as Error).message));}
      finally{if(mounted.current)setPending(n=>n-1);}
    });
  }
  function refresh(spec:HarnessSpec){
    const revision=(checks.current[spec.id]??0)+1;checks.current[spec.id]=revision;
    setChecking(rows=>({...rows,[spec.id]:true}));
    void discoverModels(spec).then(catalog=>{if(mounted.current&&checks.current[spec.id]===revision)setCatalogs(rows=>({...rows,[spec.id]:catalog}));}).catch(reason=>{if(mounted.current&&checks.current[spec.id]===revision)setError(String((reason as Error).message));}).finally(()=>{if(mounted.current&&checks.current[spec.id]===revision)setChecking(rows=>({...rows,[spec.id]:false}));});
  }
  const selectedSpec=harnesses.find(h=>h.spec.id===selected)?.spec;
  const selectedKey=selectedSpec?connectionKey(selectedSpec):'';
  useEffect(()=>{if(!admin||!selected||!selectedKey)return;const timer=setTimeout(()=>{const spec=current.current.find(h=>h.spec.id===selected)?.spec;if(spec)refresh(spec);},350);return()=>clearTimeout(timer);},[admin,selected,selectedKey]);
  useEffect(()=>{const ready=(event:Event)=>{const id=(event as CustomEvent<{id:string}>).detail?.id;const spec=current.current.find(row=>row.spec.id===id)?.spec;if(spec)refresh(spec);};window.addEventListener('workbench:provider-ready',ready);return()=>window.removeEventListener('workbench:provider-ready',ready);},[]);
  async function removeProvider(id:string){
    try{
      await queue.current;
      const spec=current.current.find(row=>row.spec.id===id)?.spec;if(!spec)return;
      await saveHarness({...spec,archived:true});
      const rows=current.current.filter(row=>row.spec.id!==id);current.current=rows;setHarnesses(rows);setSelected(rows[0]?.spec.id||'');
      setPreferences(previous=>{const next={...previous};delete next[id];localStorage.setItem('workbench.provider-model-preferences',JSON.stringify(next));return next;});
      setNotice('Provider deleted');
    }catch(reason){setError(String((reason as Error).message));}
  }
  function card(harness:Harness,mode:'list'|'editor'){
    const spec=harness.spec,prefs=preferences[spec.id]??emptyPreferences;
    return <ProviderInstanceCard key={spec.id} setup={mode==='editor'&&spec.kind==='acp'?<ProviderSetupSection environmentId="local" environmentLabel="This computer" instanceId={spec.id} provider={providerFromCatalog(spec,catalogs[spec.id])} binaryPath={spec.executable} enabled={spec.enabled!==false} readOnly={!admin||pending>0} onEnable={()=>update(spec.id,{...instanceFor(spec),enabled:true})}/>:undefined} instanceId={spec.id} instance={instanceFor(spec)} driverOption={definitionFor(spec)} liveProvider={catalogs[spec.id]?providerFromCatalog(spec,catalogs[spec.id]):undefined} mode={mode} selected={selected===spec.id} onSelect={()=>setSelected(spec.id)} readOnly={!admin} canWriteSettings={admin} onUpdate={instance=>update(spec.id,instance)} onDelete={admin&&!['codex','claude','dsh-acp'].includes(spec.id)?()=>{void removeProvider(spec.id);}:undefined} headerAction={<Button size="icon-xs" variant="ghost-muted" disabled={!admin||checking[spec.id]} onClick={()=>refresh(spec)} aria-label={`Refresh ${instanceFor(spec).displayName} models`}><RefreshCwIcon className={checking[spec.id]?'animate-spin':''}/></Button>} hiddenModels={prefs.hidden} favoriteModels={prefs.favorites} modelOrder={prefs.order} onHiddenModelsChange={hidden=>preference(spec.id,{hidden:[...hidden]})} onFavoriteModelsChange={favorites=>preference(spec.id,{favorites:[...favorites]})} onModelOrderChange={order=>preference(spec.id,{order:[...order]})}/>;
  }
  function newPreset(from?:Preset){setDraft({id:'preset-'+crypto.randomUUID().slice(0,8),name:'',harness:from?.harness||selectedSpec?.id||presets[0]?.harness||harnesses[0]?.spec.id||'codex',model:from?.model??null});}
  return <div className="t3-preset-ui dark mt-6 rounded-xl bg-background p-4 text-foreground sm:p-6"><TooltipProvider delay={250}>
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><h2 className="text-lg font-semibold">Providers</h2><p className="mt-1 text-sm text-muted-foreground">Configure provider instances and their models.</p></div><div className="flex shrink-0 flex-col items-end gap-2">{admin&&<Button variant="outline" size="sm" onClick={()=>setAdding('acpRegistry')}><PlusIcon/>ACP Registry</Button>}<span role="status" className="text-xs text-muted-foreground">{pending?'Saving…':notice}</span></div></div>
    {error&&<div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-destructive/30 px-4 py-3 text-sm text-destructive"><span>{error}</span>{selectedSpec&&<Button variant="outline" size="xs" onClick={()=>update(selectedSpec.id,instanceFor(selectedSpec))}>Retry save</Button>}</div>}
    <div className="@container/providers">
      <SettingsGroup divided={false} className="@min-[48rem]/providers:h-[min(44rem,calc(100dvh-11rem))] @min-[48rem]/providers:min-h-[32rem] overflow-hidden @min-[48rem]/providers:grid @min-[48rem]/providers:grid-cols-[17rem_minmax(0,1fr)]">
        <div className="border-b border-border/60 bg-muted/10 @min-[48rem]/providers:flex @min-[48rem]/providers:min-h-0 @min-[48rem]/providers:flex-col @min-[48rem]/providers:border-r @min-[48rem]/providers:border-b-0"><ScrollArea scrollFade chainVerticalScroll className="@min-[48rem]/providers:min-h-0 @min-[48rem]/providers:flex-1"><div className="divide-y divide-border/50">{harnesses.map(h=>card(h,'list'))}{admin&&<button type="button" className="flex w-full items-center gap-3 px-4 py-4 text-left text-sm text-muted-foreground hover:bg-muted/25 hover:text-foreground" onClick={()=>setAdding('codex')}><PlusIcon className="size-4 shrink-0"/>Add provider</button>}</div></ScrollArea></div>
        <div className="min-w-0 @min-[48rem]/providers:min-h-0">{selectedSpec?<ScrollArea scrollFade chainVerticalScroll className="@min-[48rem]/providers:h-full"><div className="space-y-6 p-4">{checking[selected]&&<p role="status" className="text-xs text-muted-foreground">Reading provider models…</p>}{card({spec:selectedSpec,probe:null},'editor')}</div></ScrollArea>:<div role="status" className="p-6 text-sm text-muted-foreground">{loading?'Loading providers…':'No providers configured.'}</div>}</div>
      </SettingsGroup>
    </div>
    <div className="mt-8 space-y-6">
      <SettingsSection title="Agent + model presets" headerAction={admin?<Button variant="outline" size="xs" disabled={loading} onClick={()=>newPreset()}><PlusIcon/>Add preset</Button>:undefined}>
        {presets.map(pair=><SettingsRow key={pair.id} title={pair.name} description={`${harnesses.find(h=>h.spec.id===pair.harness)?.spec.name||pair.harness} · ${pair.model||'Agent default'}`} control={admin?<div className="flex gap-1"><Button variant="ghost-muted" size="icon-xs" aria-label={`Edit preset ${pair.name}`} onClick={()=>{setDraft({...pair});setSelected(pair.harness);}}><PencilIcon/></Button><Button variant="ghost-muted" size="icon-xs" aria-label={`Duplicate preset ${pair.name}`} onClick={()=>newPreset(pair)}><CopyIcon/></Button><Button variant="ghost-destructive" size="icon-xs" aria-label={`Delete preset ${pair.name}`} disabled={presets.length<2} onClick={()=>void deletePreset(pair.id).then(()=>{setPresets(rows=>rows.filter(row=>row.id!==pair.id));setNotice('Preset deleted');}).catch(reason=>setError(String(reason.message)))}><Trash2Icon/></Button></div>:undefined}/>)}
      </SettingsSection>
      {draft&&admin&&<PresetEditor key={draft.id} initial={draft} harnesses={harnesses} catalogs={catalogs} preferences={preferences} onProviderSelected={setSelected} onCancel={()=>setDraft(null)} onConfigure={id=>{setSelected(id);document.querySelector('.t3-preset-ui')?.scrollIntoView({block:'start',behavior:'smooth'});}} onSaved={saved=>{setPresets(rows=>rows.some(p=>p.id===saved.id)?rows.map(p=>p.id===saved.id?saved:p):[...rows,saved]);setDraft(null);setNotice('Preset saved');}}/>}
    </div>
    {adding&&<T3AddProviderDialog initialDriver={adding} onClose={()=>setAdding(null)} onAdded={spec=>{setHarnesses(rows=>[...rows,{spec,probe:null}]);setSelected(spec.id);setAdding(null);setNotice('Provider added');}}/>}
  </TooltipProvider><div id="t3-preset-portals" className="t3-preset-ui dark"/></div>;
}
