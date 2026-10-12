import {api} from './api';
import {WorkflowSpec} from './projectWorkflows';
export type ProjectConfiguration={version:number;resource_ids:string[];workflow:WorkflowSpec|null};
export type IdeaSources={version:number;mode:'inherit'|'custom'|'pinned';resource_ids:string[]};
export const configuration=(project:string)=>api<ProjectConfiguration>(`/projects/${project}/configuration`);
