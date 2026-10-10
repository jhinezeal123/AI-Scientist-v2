import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';

// Test the pure selector with the same compiler as the frontend, on every
// supported Node version; no browser, provider, credentials or Kaggle required.
const source=await readFile(new URL('../src/researchActivity.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {stageRecords,stageActivity,resultText,outputText}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const task=(id,sessionId)=>({id,seat:'shared',request_id:id,state:'DONE',result:{session_id:sessionId,summary:'result '+id}});
const event=(id,task_id,session_id,text)=>({id,task_id,session_id,seat_id:'shared',kind:'output',data:{text}});
const flow={id:'chosen-flow',state:{stage:'report',status:'DONE',events:[
  {stage:'draft',kind:'agent_queued',task_id:'draft-task'},
  {stage:'draft',kind:'agent_completed',task_id:'draft-task'},
  {stage:'report',kind:'agent_queued',task_id:'report-task'},
  {stage:'report',kind:'agent_completed',task_id:'report-task'},
]}};
const team={tasks:[task('other-workflow','other-session'),task('draft-task','draft-session'),task('report-task','report-session')],sessions:[
  {id:'other-session',seat_id:'shared',task_id:'other-workflow'},
  {id:'draft-session',seat_id:'shared',task_id:'draft-task'},
  {id:'report-session',seat_id:'shared',task_id:'report-task'},
]};

test('shared agent never mixes stages or workflows, including session-only events',()=>{
  const records=stageRecords('draft',flow,team,[event(1,'other-workflow','other-session','foreign'),event(2,'report-task','report-session','report'),event(3,'draft-task','draft-session','draft'),event(4,null,'draft-session','legacy'),event(5,null,null,'unscoped'),event(6,'other-workflow','draft-session','conflicting task identity')]);
  assert.deepEqual(records.tasks.map(row=>row.id),['draft-task']);
  assert.deepEqual(records.sessions.map(row=>row.id),['draft-session']);
  assert.deepEqual(records.output.map(row=>row.id),[3,4]);
});
test('no selected workflow exposes no team history',()=>{
  const records=stageRecords('draft',null,team,[event(1,'draft-task','draft-session','draft')]);
  assert.deepEqual(records,{receipts:[],tasks:[],sessions:[],output:[]});
});
test('a legacy session is linked through the saved task result, not seat name',()=>{
  const legacy={...team,sessions:[{id:'draft-session',seat_id:'shared'},{id:'other-session',seat_id:'shared'}]};
  assert.deepEqual(stageRecords('draft',flow,legacy,[]).sessions.map(row=>row.id),['draft-session']);
  assert.deepEqual(stageRecords('draft',flow,{...legacy,sessions:[{id:'draft-session',task_id:'other-workflow'}]},[]).sessions,[]);
});
test('waiting for human approval supersedes an already completed agent response',()=>{
  assert.equal(stageActivity('draft',{...flow,state:{...flow.state,stage:'draft',status:'WAITING'}}),'waiting');
});
test('active stage stays active between its completed action turns',()=>{
  assert.equal(stageActivity('draft',{...flow,state:{...flow.state,stage:'draft',status:'RUNNING'}}),'running');
});
test('pause, unknown and failure keep earlier completed stages intact',()=>{
  for(const [status,expected] of [['PAUSED','paused'],['UNKNOWN','unknown'],['FAILED','failed']]){
    const updated={...flow,state:{...flow.state,status}};
    assert.equal(stageActivity('report',updated),expected);
    assert.equal(stageActivity('draft',updated),'done');
  }
  assert.equal(stageActivity('ideation',flow),'idle');
});
test('approval refusal is kept verbatim; finish and report use their saved response',()=>{
  assert.match(resultText({result:{summary:'{"approve":false,"reason":"outside grant"}'}}),/"approve": false/);
  assert.equal(resultText({result:{summary:'{"action":"finish","result":{"summary":"Measured result"}}'}}),'Measured result');
  assert.equal(resultText({result:{summary:'{"response":"# Report"}'}}),'# Report');
  assert.equal(resultText({result:{error:'Failed'}}),'Failed');
});
test('native output hides bookkeeping while preserving agent text and plain output',()=>{
  assert.equal(outputText(event(1,null,null,'{"type":"turn.started"}')),'');
  assert.equal(outputText(event(2,null,null,'{"item":{"type":"agent_message","text":"Actual response"}}')),'Actual response');
  assert.equal(outputText(event(3,null,null,'Actual streamed text')),'Actual streamed text');
  assert.equal(outputText(event(4,null,null,JSON.stringify({item:{type:'agent_message',text:JSON.stringify({summary:JSON.stringify({response:'Readable report'})})}}))),'Readable report');
});
