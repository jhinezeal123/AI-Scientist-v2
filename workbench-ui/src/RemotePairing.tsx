import {useState} from 'react';
import {exchangePair} from './remoteApi';
import useAgentAction from './useAgentAction';

export default function RemotePairing({onConnected}:{onConnected:()=>Promise<void>}){
  const [pairId,setPairId]=useState(''),[code,setCode]=useState(''),[name,setName]=useState('Personal device');
  const {busy,error,action}=useAgentAction();
  return <form className="stack" onSubmit={e=>{e.preventDefault();void action(async()=>{await exchangePair(pairId,code,name);await onConnected();});}}>
    <h3>Ghép thiết bị qua HTTPS private</h3>{error&&<p role="alert" className="alert error">{error}</p>}
    <label>Pairing ID<input required value={pairId} onChange={e=>setPairId(e.target.value)}/></label>
    <label>Mã<input required type="password" value={code} onChange={e=>setCode(e.target.value)}/></label>
    <label>Tên thiết bị<input required value={name} onChange={e=>setName(e.target.value)}/></label>
    <button disabled={busy}>Ghép thiết bị</button>
  </form>;
}
