import {api} from './api';
import {WorkflowSpec} from './projectWorkflows';
export type RunConfiguration=Pick<WorkflowSpec,'mode'|'benchmark_id'|'desired_output'|'account'|'accelerator'|'ttl_seconds'|'execution_seconds'|'output_bytes'|'research'|'search'>;
export type ProjectConfiguration={version:number;resource_ids:string[];run:RunConfiguration;workflow:WorkflowSpec|null};
export type IdeaSources={version:number;mode:'inherit'|'custom'|'pinned';resource_ids:string[]};
export const configuration=(project:string)=>api<ProjectConfiguration>(`/projects/${project}/configuration`);
