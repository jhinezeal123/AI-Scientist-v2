import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ArtifactsPage from './ArtifactsPage';
import ProjectTreePage from './ProjectTreePage';
import SettingsPage from './SettingsPage';
import MultiAgentSettingsPage from './MultiAgentSettingsPage';
import SettingsLink from './SettingsLink';
import './styles.css';

const page=new URLSearchParams(window.location.search);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <SettingsLink/>
  {page.get('page')==='settings' ? (page.get('tab')==='multi-agent' ? <MultiAgentSettingsPage/> : <SettingsPage/>) : page.get('page')==='artifacts' ? <ArtifactsPage projectId={page.get('project') || ''} runId={page.get('run') || ''} outputOnly={page.get('view')==='output'}/>
    : page.get('page')==='run-tree' ? <ProjectTreePage projectId={page.get('project') || ''}/> : <App/>}
</React.StrictMode>);
