import test,{beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);

// Run the actual lightweight API clients with a fixture transport, without a browser.
const encode=code=>'data:text/javascript;base64,'+Buffer.from(code).toString('base64');
async function compile(file,imports={}){
  const source=await readFile(new URL('../src/'+file,import.meta.url),'utf8');
  let code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
  for(const [name,url] of Object.entries(imports))code=code.replaceAll("'"+name+"'",JSON.stringify(url)).replaceAll(JSON.stringify(name),JSON.stringify(url));
  return encode(code);
}
const shared=await compile('agentApi.ts');
const remote=await import(await compile('remoteApi.ts',{'./agentApi':shared}));
const workflows=await import(await compile('projectWorkflows.ts',{'./agentApi':shared}));
beforeEach(()=>{
  const values=new Map();
  globalThis.sessionStorage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
});

test('device administration survives unavailable project lookup',async()=>{
  const devices=[{id:'device',name:'Fixture'}],requests=[];
  globalThis.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>devices};};
  const result=await remote.readRemoteSettings(async()=>{throw new Error('Projects unavailable');},true);
  assert.equal(result.projects.status,'rejected');
  assert.deepEqual(result.devices,{status:'fulfilled',value:devices});
  assert.deepEqual(requests,['/api/agent-management/devices']);
});

test('lost save response retries the same project grant without changing preset configuration',async()=>{
  const spec={...workflows.defaults('chosen-preset'),goal:'Verify checksum',account:'fixture'};
  const requests=[];
  globalThis.fetch=async(url,options)=>{requests.push({url,options});if(requests.length===1)throw new Error('Lost response');return {ok:true,json:async()=>({id:'saved-grant',spec})};};
  await assert.rejects(workflows.saveWorkflow('project',spec),/Lost response/);
  const saved=await workflows.saveWorkflow('project',spec);
  assert.equal(saved.id,'saved-grant');
  assert.equal(requests.length,2);
  assert.equal(requests[0].url,'/api/agent-management/projects/project/workflows');
  assert.equal(requests[0].options.method,'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body),JSON.parse(requests[1].options.body));
  assert.match(JSON.parse(requests[0].options.body).request_id,/^[a-f0-9]{32}$/);
  assert.deepEqual(spec.stages.proposal,{actor:'agent',preset_id:'chosen-preset'});
});

test('provider catalog loads without executing provider probes and saves configuration through the preset API',async()=>{
  const presets=await import(await compile('agentPresets.ts',{'./agentApi':shared}));
  const requests=[];
  globalThis.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>[]};};
  await presets.listHarnesses(true);
  const spec={id:'custom-agent',kind:'acp',executable:'agent.exe',args:['argument with spaces'],models:['custom-model']};
  await presets.saveHarness(spec);
  await presets.checkHarness(spec);
  assert.equal(requests[0].url,'/api/agent-management/harnesses?probe=false&details=true');
  assert.equal(requests[1].options.method,'PUT');
  assert.deepEqual(JSON.parse(requests[1].options.body),spec);
  assert.equal(requests[2].url,'/api/agent-management/harnesses/custom-agent/probe');
});

const modelBridge=await compile('vendor/t3code/bridge/model.ts');
const setup=await import(await compile('T3ProviderSetup.tsx',{'./vendor/t3code/bridge/model':modelBridge}));
const ordering=await compile('vendor/t3code/modelOrdering.ts',{'effect/Array':pathToFileURL(require.resolve('effect/Array')).href,'effect/Order':pathToFileURL(require.resolve('effect/Order')).href});
const choices=await import(await compile('providerModelOptions.ts',{'./vendor/t3code/modelOrdering':ordering}));

test('T3 provider form preserves literal arguments, redacted secrets and custom model metadata',()=>{
  const spec={id:'named',kind:'acp',name:'Named provider',enabled:true,executable:'agent.exe',
    args:['--config','path with spaces'],config_directory:'',environment:{API_KEY:'__WORKBENCH_STORED_SECRET__',BASE_URL:'https://fixture.invalid'},
    environment_sensitive:['API_KEY'],custom_models:[{slug:'custom',name:'Custom model',capabilities:{optionDescriptors:[]}}]};
  const instance=setup.instanceFor(spec);
  assert.equal(instance.environment[0].value,'');
  assert.equal(instance.environment[0].valueRedacted,true);
  const saved=setup.specFromInstance(spec,{...instance,displayName:'Renamed'});
  assert.deepEqual(saved.args,spec.args);
  assert.deepEqual(saved.environment,spec.environment);
  assert.deepEqual(saved.environment_sensitive,['API_KEY']);
  assert.deepEqual(saved.custom_models,spec.custom_models);
  assert.equal(saved.name,'Renamed');
  assert.throws(()=>setup.specFromInstance(spec,{...instance,environment:[instance.environment[0],instance.environment[0]]}),/unique/);
});

test('model picker honors T3 visibility, favorites and ordering separately for each provider',()=>{
  const spec={id:'one',kind:'native_codex',custom_models:[{slug:'custom',name:'Custom model'}]};
  const catalog={models:[{slug:'a',name:'A'},{slug:'b',name:'B'},{slug:'c',name:'C'},{slug:'custom',name:'stale cached name',isCustom:true}]};
  const prefs={hidden:['b'],favorites:['c'],order:['a','c']};
  assert.deepEqual(choices.providerModelOptions(spec,catalog,prefs).map(m=>m.slug),['c','a','custom']);
  assert.deepEqual(choices.providerModelOptions(spec,catalog,prefs,'b').map(m=>m.slug),['c','a','b','custom']);
  assert.deepEqual(choices.providerModelOptions({id:'other',kind:'acp'}, {models:[{slug:'only-other',name:'Only other'}]},prefs).map(m=>m.slug),['only-other']);
});

test('model discovery uses the selected draft and does not implicitly save it',async()=>{
  const presets=await import(await compile('agentPresets.ts',{'./agentApi':shared}));
  const requests=[];
  globalThis.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({models:[]})};};
  const spec={id:'profile-two',kind:'native_codex',config_directory:'alternate profile'};
  await presets.discoverModels(spec);
  assert.equal(requests.length,1);
  assert.equal(requests[0].url,'/api/agent-management/harnesses/profile-two/models');
  assert.equal(requests[0].options.method,'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body),spec);
});
