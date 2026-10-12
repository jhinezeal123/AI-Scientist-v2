import AgentAccess from './AgentAccess';
import {agentCall} from './agentApi';
import SettingsNavigation,{SettingsTab} from './SettingsNavigation';
import {lazy,Suspense} from 'react';
import SlackSettings from './SlackSettings';
import RemoteSettings from './RemoteSettings';
import RemotePairing from './RemotePairing';
import RemoteResearchControls from './RemoteResearchControls';

const remoteProjects=()=>agentCall<{id:string;name:string}[]>('/workflow-projects');
const PresetSettings=lazy(()=>import('./PresetSettings'));

// Page composition only: each feature owns its state, requests and policy.
export default function AgentSettingsPage(){
  const query=new URLSearchParams(location.search).get('tab');
  const active:SettingsTab=query==='slack'?'slack':query==='remote'?'remote':'config-agent';
  return <><aside className="rail settings-rail"><a className="brand" href="/" style={{textDecoration:'none'}}><span className="brand-mark">∿</span><span>AI SCIENTIST<small>LOCAL WORKBENCH</small></span></a>
    <a href="/">← Quay về Workbench</a><SettingsNavigation active={active}/>
    <div className="rail-footer">Cài đặt dùng chung<br/>cho các project trên máy này.</div>
  </aside><main className="settings-page team-settings"><header><div><span className="eyebrow">SETTINGS</span><h1>{active==='config-agent'?'Config agent':active==='slack'?'Slack':'Remote'}</h1></div></header>
    <AgentAccess renderConnection={active==='remote'?onConnected=><RemotePairing onConnected={onConnected}/>:undefined}>{identity=><>
      <button onClick={()=>void agentCall('/logout','POST').then(()=>location.reload())}>Đăng xuất</button>
      {active==='config-agent'&&<Suspense fallback={<p role="status">Đang tải cấu hình agent…</p>}><PresetSettings admin={identity.scopes.includes('admin')}/></Suspense>}
      {active==='slack'&&<SlackSettings admin={identity.scopes.includes('admin')}/>}
      {active==='remote'&&<RemoteSettings identity={identity} loadProjects={remoteProjects} renderProject={id=><RemoteResearchControls key={id} projectId={id}/>}/>}
    </>}</AgentAccess>
  </main></>;
}
