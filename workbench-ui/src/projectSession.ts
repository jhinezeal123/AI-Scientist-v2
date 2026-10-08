import {RunMode} from './api';

export type ProjectSession = {tab:'Library'|'Idea'|'Run';ideaId:string;sourceIds:string[];runId:string;mode:RunMode};
const empty:ProjectSession={tab:'Library',ideaId:'',sourceIds:[],runId:'',mode:'training_research'};
const key=(projectId:string)=>`workbench.session.${projectId}`;
const validId=(value:unknown):value is string=>typeof value==='string' && /^[0-9a-f]{32}$/.test(value);

/** Browser preferences only; discussions, approvals and outputs stay in the backend. */
export function readProjectSession(projectId:string):ProjectSession {
  try {
    const saved=JSON.parse(localStorage.getItem(key(projectId)) || '{}');
    return {
      tab:['Library','Idea','Run'].includes(saved.tab) ? saved.tab : 'Library',
      mode:saved.mode==='etc' ? 'etc' : 'training_research',
      ideaId:validId(saved.ideaId) ? saved.ideaId : '',
      runId:validId(saved.runId) ? saved.runId : '',
      sourceIds:Array.isArray(saved.sourceIds) ? [...new Set<string>(saved.sourceIds.filter(validId))].slice(0,30) : [],
    };
  } catch {return {...empty,sourceIds:[]};}
}

export function saveProjectSession(projectId:string,session:ProjectSession) {
  if (!validId(projectId))return;
  try {localStorage.setItem(key(projectId),JSON.stringify(session));} catch { /* Storage can be unavailable. */ }
}

export function lastProject():string {
  try {return localStorage.getItem('workbench.project') || '';} catch {return '';}
}
export function rememberProject(projectId:string) {
  try {localStorage.setItem('workbench.project',projectId);} catch { /* Saved server data remains usable. */ }
}

export function forgetProject(projectId:string) {
  try {
    localStorage.removeItem(key(projectId));
    if (lastProject()===projectId)localStorage.removeItem('workbench.project');
  } catch { /* Server deletion does not depend on browser preferences. */ }
}
