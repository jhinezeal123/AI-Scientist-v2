import {agentCall,teamIntent} from './agentApi';
import {ResearchPlan} from './api';

export const stages=[['ideation','Ideathon'],['literature','Literature / novelty'],['proposal','Proposal'],['approval','Duyệt proposal'],['execution','Thực thi'],['draft','Draft'],['tuning','Tuning'],['research','Research'],['ablation','Ablation'],['analysis','Phân tích'],['summary','Summary'],['report','Report'],['plots','Plots'],['citations','Thu thập citation'],['vision','VLM đánh giá hình'],['writeup','Viết bài'],['review','Review']] as const;
export type Binding={actor:'human'|'agent';preset_id?:string|null;harness?:string|null;model?:string|null;ask?:boolean};
export type WorkflowSpec={goal:string;mode:'training_research'|'etc';benchmark_id:string|null;resource_ids:string[];desired_output:string;stages:Record<string,Binding>;allow_agent_approval:boolean;require_run_approval:boolean;max_runs:number;ttl_seconds:number;execution_seconds:number;max_agent_calls:number;output_bytes:number;accelerator:string;account:string;research:ResearchPlan;ideation:{candidates:number};search:{enabled:boolean;stage_iterations:number[];num_drafts:number;debug_prob:number;max_debug_depth:number;num_workers:number;scale_experiments:boolean}};
export type HumanInput={id:string;stage:string;state:string;prompt:{kind:string;candidate?:unknown;prompt?:unknown;schema?:unknown;approval_allowed?:boolean;questions?:string[];proposal_round?:number;parent_run_id?:string|null}};
export type N8nStatus={ready:boolean;editor_url:string;workflow_url:string;agent_workflow_url:string;execution_url?:string|null;callback_failed?:boolean};
export type Flow={id:string;project_id:string;spec:WorkflowSpec;state:{status:string;stage:string;iteration:number;calls:number;runs:string[];run_id:string|null;idea_id:string|null;proposal_id:string|null;generation:number;events:{stage:string;kind:string;at:string;execution_id?:string;preset_id?:string}[];error?:string};inputs?:HumanInput[];n8n?:N8nStatus};
export type WorkflowOptions={project_id:string;resources:{id:string;title:string}[];benchmarks:{id:string;title?:string;name?:string}[];accounts:{account:string;username:string;configured:boolean}[];n8n:N8nStatus;configuration:import('./projectConfiguration').ProjectConfiguration;literature?:{configured:boolean}};
export const workflowBase=(project:string)=>'/projects/'+project+'/workflows';
export async function saveWorkflow(project:string,spec:WorkflowSpec){
  const intent=await teamIntent(project+':n8n-workflow',spec);
  const result=await agentCall<Flow>(workflowBase(project),'POST',{request_id:intent.id.replaceAll('-',''),spec});
  intent.ack();return result;
}
export function defaults(preset='default'):WorkflowSpec{
  return {goal:'',mode:'training_research',benchmark_id:null,resource_ids:[],desired_output:'',stages:Object.fromEntries(stages.map(([stage])=>[stage,{actor:['ideation','approval'].includes(stage)?'human':'agent',preset_id:['ideation','approval'].includes(stage)?null:preset}])),allow_agent_approval:false,require_run_approval:true,max_runs:1,ttl_seconds:600,execution_seconds:480,max_agent_calls:100,output_bytes:1000000,accelerator:'cpu',account:'',research:{summary:false,report:false,plots:false,writeup:'none',review:false,literature:true,literature_rounds:5,citations:false,citation_rounds:20,vlm:false,seeds:[],seed_stages:[2,3],reflections:1},ideation:{candidates:3},search:{enabled:false,stage_iterations:[3,3,3,3],num_drafts:3,debug_prob:.5,max_debug_depth:3,num_workers:1,scale_experiments:false}};
}
