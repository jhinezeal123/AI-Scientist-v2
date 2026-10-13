import {api} from './api';
import {WorkflowSpec} from './projectWorkflows';
export type RunConfiguration=Pick<WorkflowSpec,'account'|'accelerator'|'ttl_seconds'|'execution_seconds'|'output_bytes'|'search'>;
export type IdeaConfiguration=Pick<WorkflowSpec,'goal'|'mode'|'benchmark_id'|'desired_output'|'research'>;
export type ProjectConfiguration={version:number;resource_ids:string[];idea:IdeaConfiguration;run:RunConfiguration;workflow:WorkflowSpec|null};
export type RunExecutionConfiguration={version:number;run_id:string;idea_id:string;configuration:RunConfiguration;approved:boolean;
  approval_sha256:string|null;limits:{execution_seconds:number|null;output_bytes:number|null};planned_search:WorkflowSpec['search'];
  mode:string;proposal_id:string;proposal_version:number;execution_requirements?:{accelerators:string[];reason:string}|null};
export type IdeaSources={version:number;mode:'inherit'|'custom'|'pinned';resource_ids:string[]};
export const configuration=(project:string)=>api<ProjectConfiguration>(`/projects/${project}/configuration`);
export const sameExperimentStrategy=(a:RunConfiguration['search'],b:RunConfiguration['search'])=>
  !a.enabled&&!b.enabled||JSON.stringify(a)===JSON.stringify(b);
