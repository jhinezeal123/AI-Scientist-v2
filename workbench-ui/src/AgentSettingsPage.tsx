import {lazy,Suspense} from 'react';
import AgentAccess from './AgentAccess';
import {agentCall} from './agentApi';
import SettingsNavigation from './SettingsNavigation';
const PresetSettings=lazy(()=>import('./PresetSettings'));
export default function AgentSettingsPage(){return <>
  <aside className="rail settings-rail"><a className="brand" href="/" style={{textDecoration:'none'}}><span className="brand-mark">∿</span><span>AI SCIENTIST<small>LOCAL WORKBENCH</small></span></a><a href="/">← Quay về Workbench</a><SettingsNavigation active="config-agent"/><div className="rail-footer">Cài đặt dùng chung<br/>cho các project trên máy này.</div></aside>
  <main className="settings-page team-settings"><header><div><span className="eyebrow">SETTINGS</span><h1>Config agent</h1></div></header><AgentAccess>{identity=><><button onClick={()=>void agentCall('/logout','POST').then(()=>location.reload())}>Đăng xuất</button><Suspense fallback={<p role="status">Đang tải cấu hình agent…</p>}><PresetSettings admin={identity.scopes.includes('admin')}/></Suspense></>}</AgentAccess></main>
</>;}
