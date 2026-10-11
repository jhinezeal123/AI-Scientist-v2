import {useCallback,useState} from 'react';

// Shared async UI state, without feature-specific data or decisions.
export default function useAgentAction(){
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const action=useCallback(async(work:()=>Promise<void>)=>{
    setBusy(true);setError('');setNotice('');
    try{await work();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  },[]);
  return {busy,error,notice,setNotice,action};
}
