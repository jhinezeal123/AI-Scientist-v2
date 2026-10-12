import {ReactNode,useEffect,useState} from 'react';
import {Identity} from './agentAuth';
import {Device,ProjectReference,Pairing,listDevices,pairProject,revokeDevice,readRemoteSettings} from './remoteApi';
import useAgentAction from './useAgentAction';

type Props={identity:Identity;loadProjects:()=>Promise<ProjectReference[]>;renderProject:(id:string)=>ReactNode};
export default function RemoteSettings({identity,loadProjects,renderProject}:Props){
  const admin=identity.scopes.includes('admin');
  const [projects,setProjects]=useState<ProjectReference[]>([]),[selected,setSelected]=useState('');
  const [research,setResearch]=useState(false),[devices,setDevices]=useState<Device[]>([]),[pair,setPair]=useState<Pairing|null>(null);
  const {busy,error,notice,action}=useAgentAction();
  useEffect(()=>{let stopped=false;void action(async()=>{
    const result=await readRemoteSettings(loadProjects,admin);
    if(stopped)return;
    if(result.projects.status==='fulfilled'){setProjects(result.projects.value);setSelected(result.projects.value[0]?.id||'');}
    if(result.devices.status==='fulfilled')setDevices(result.devices.value);
    if(result.projects.status==='rejected')throw result.projects.reason;
    if(result.devices.status==='rejected')throw result.devices.reason;
  });return()=>{stopped=true;};},[admin,loadProjects,action]);
  return <>{error&&<p role="alert" className="alert error">{error}</p>}{notice&&<p role="status" className="alert">{notice}</p>}
    <section className="panel"><h2>Thiết bị cá nhân</h2>{admin&&<>
      <label>Project<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Chọn project</option>{projects.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
      <label><input type="checkbox" checked={research} onChange={e=>setResearch(e.target.checked)}/>Cho thiết bị bắt đầu/dừng workflow và trả lời bước chờ human</label>
      <button disabled={busy||!selected} onClick={()=>void action(async()=>setPair(await pairProject(selected,research)))}>Tạo mã kết nối</button>
      {pair&&<div className="alert"><p>Pairing ID: <code>{pair.pairing_id}</code></p><p>Mã: <code>{pair.code}</code></p><p>Hết hạn: {pair.expires_at}</p></div>}
      {devices.map(d=><article key={d.id}><strong>{d.name}</strong><p>{d.revoked?'Đã thu hồi':'Còn hiệu lực'} · {d.expires_at}</p><button disabled={busy||d.revoked} onClick={()=>void action(async()=>{await revokeDevice(d.id);setDevices(await listDevices());})}>Thu hồi</button></article>)}
    </>}{!admin&&projects.map(t=><p key={t.id}>{t.name} · Thiết bị đã kết nối</p>)}</section>
    {!admin&&selected&&renderProject(selected)}
  </>;
}
