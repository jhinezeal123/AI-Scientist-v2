export type Project = {id: string; name: string; created_at: string};
export type Resource = {id: string; kind: 'text'|'url'|'dataset'; title: string; url: string|null;
  content: string; status: string; version: number; content_sha256: string};
export type PlanBody = {needs_clarification: boolean; questions: string[]; paraphrase: string;
  objective?: string; data_refs?: string[]; split?: {method:string;group_key:string;subset:string;seed:number};
  metric?: {name:string;direction:string;definition:string}; implementation_steps?: string[];
  budget?: {coder_calls:number;training_attempts:number;training_seconds:number;output_bytes:number}; expected_outputs?: string[]};
export type Idea = {id: string; title: string; text: string; state: string; error: string|null; created_at: string;
  conversation: ({role:'user';text:string;reply_to:string}|{role:'assistant';proposal_id:string;version:number;body:PlanBody})[]};
export const ideaTitle=(idea:Idea)=>idea.title || 'Chưa đặt tiêu đề';
export type Context = {context_sha256: string; snapshot: {project_id: string;
  idea: {id: string; text: string}; resources: Resource[]}};
export type History = {proposals: {id: string; version: number; state: string; context_sha256: string}[];
  runs: {id: string; proposal_id: string; proposal_version?:number; idea_id?:string|null; state: string; error: string|null;
    purpose?: string; idea_text?:string; proposal_objective?:string; context_sha256?:string;
    source_refs?:{id:string;title:string;kind:string;version:number;content_sha256:string}[];
    code_sha256?:string|null; artifacts?:string[];
    result_metric?: {name:string;direction:string;final_value:number;best_value:number};report_available?:boolean}[]};
export type Proposal = {id:string;idea_id:string;version:number;state:string;body:PlanBody;
  context_sha256:string;context_snapshot:Context['snapshot'];approved_at:string|null};

export async function api<T>(path: string, method='GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {method,
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {
    let detail: unknown;
    try {detail = (await response.json()).detail;} catch {detail = response.statusText;}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}
