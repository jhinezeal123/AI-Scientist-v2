import {ReactNode,useEffect,useState} from 'react';
import {teamApi} from './agentApi';
import {Identity,readIdentity} from './agentAuth';

export default function AgentAccess({children,renderConnection}:{children:(identity:Identity)=>ReactNode;renderConnection?:(onConnected:()=>Promise<void>)=>ReactNode}){
  const [identity,setIdentity]=useState<Identity|null>(null),[loading,setLoading]=useState(true),[token,setToken]=useState(''),[error,setError]=useState('');
  async function identityRead(){setIdentity(await readIdentity());}
  useEffect(()=>{void identityRead().catch(()=>{}).finally(()=>setLoading(false));},[]);
  if(loading)return <p role="status">Đang đọc cấu hình agent…</p>;
  if(identity)return <>{children(identity)}</>;
  return <section className="panel"><h2>Kết nối Workbench</h2><p>Nhập token một lần để lưu phiên trên trình duyệt này. Token nằm trong .workbench/agent-control-token.txt.</p>{error&&<p role="alert" className="alert error">{error}</p>}<form className="stack" onSubmit={e=>{e.preventDefault();setLoading(true);setError('');void teamApi('/local-session',token,'POST').then(()=>{setToken('');return identityRead();}).catch(e=>setError(e.message)).finally(()=>setLoading(false));}}><label>Control token<input type="password" required autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label><button className="primary">Kết nối và nhớ phiên</button></form>{renderConnection?.(identityRead)}</section>;
}
