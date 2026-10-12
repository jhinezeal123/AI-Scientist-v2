import {useEffect,useState} from 'react';
import {agentCall} from './agentApi';
import {readIdentity} from './agentAuth';
import {Flow,workflowBase} from './projectWorkflows';

/** One current orchestration state feeds every project tab. */
export function useProjectWorkflow(project:string){
  const [flow,setFlow]=useState<Flow|null>(null),[error,setError]=useState('');
  useEffect(()=>{let stopped=false,inFlight=false,authenticated=false;setFlow(null);setError('');
    async function read(){if(inFlight||!project)return;inFlight=true;try{
      if(!authenticated){await readIdentity();authenticated=true;}
      const rows=await agentCall<Flow[]>(workflowBase(project));
      const row=rows.find(r=>['RUNNING','WAITING','UNKNOWN'].includes(r.state.status))||rows.find(r=>r.state.status==='PAUSED'&&(r.state.idea_id||r.inputs?.some(i=>i.state==='PENDING')));
      const value=row?await agentCall<Flow>(workflowBase(project)+'/'+row.id):null;
      if(!stopped){setFlow(value);setError('');}
    }catch(e){authenticated=false;if(!stopped)setError(e instanceof Error?e.message:String(e));}finally{inFlight=false;}}
    void read();const timer=setInterval(()=>void read(),1500);return()=>{stopped=true;clearInterval(timer);};
  },[project]);
  return {flow,error};
}
