import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ArtifactsPage from './ArtifactsPage';
import './styles.css';

const page=new URLSearchParams(window.location.search);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>
  {page.get('page')==='artifacts' ? <ArtifactsPage projectId={page.get('project') || ''} runId={page.get('run') || ''} outputOnly={page.get('view')==='output'}/> : <App/>}
</React.StrictMode>);
