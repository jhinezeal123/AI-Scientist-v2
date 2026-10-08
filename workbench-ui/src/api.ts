export type Project = {id: string; name: string; created_at: string; directory_name:string;library_path:string};
export type Resource = {id: string; kind: 'text'|'url'|'dataset'|'pdf'|'file'; title: string; url: string|null;
  content: string; status: string; version: number; content_sha256: string;
  file_path?:string;file_sha256?:string;file_bytes?:number;
  attachment?:{filename:string;original_file_path:string;original_sha256:string;original_bytes:number;
    manifest_file_path:string;manifest_sha256:string;page_count:number|null;processed_pages:number;text_pages:number;issues:string[]}};
export type PlanBody = {needs_clarification: boolean; questions: string[]; paraphrase: string;
  objective?: string; data_refs?: string[]; split?: string|Record<string,unknown>;
  metric?: string|Record<string,unknown>; implementation_steps?: string[];
  budget?: Record<string,unknown>; expected_outputs?: string[]};
export type Idea = {id: string; title: string; text: string; state: string; error: string|null; created_at: string;deleted_at?:string|null;
  conversation: ({role:'user';text:string;reply_to:string}|{role:'assistant';proposal_id:string;version:number;body:PlanBody})[]};
export const ideaTitle=(idea:Idea)=>idea.title || 'Chưa đặt tiêu đề';
export type Working = {phase:string;accelerator:string;ttl_seconds:number;started_at:string;agent_called:number;
  stop_confirmed:boolean;notebook_ref?:string;summary?:{succeeded:boolean;summary:string;limitations:string[];output_files:string[]}|null};
export type Context = {context_sha256: string; snapshot: {project_id: string;
  idea: {id: string; text: string}; resources: Omit<Resource,'content'>[]}};
export type History = {proposals: {id: string; version: number; state: string; context_sha256: string}[];
  runs: {id: string; proposal_id: string; proposal_version?:number; idea_id?:string|null; state: string; error: string|null;deleted_at?:string|null;
    purpose?: string; idea_text?:string; proposal_objective?:string; context_sha256?:string;
    source_refs?:{id:string;title:string;kind:string;version:number;content_sha256:string}[];
    code_sha256?:string|null; artifacts?:string[];execution_mode?:'ssh'|'legacy';working?:Working|null;
    result_metric?: {name:string;direction:string;final_value:number;best_value:number};report_available?:boolean}[]};
export type Proposal = {id:string;idea_id:string;version:number;state:string;body:PlanBody;
  context_sha256:string;context_snapshot:Context['snapshot'];approved_at:string|null};

export async function api<T>(path: string, method='GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {method,
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  return responseJson<T>(response);
}

async function responseJson<T>(response:Response):Promise<T> {
  await checkResponse(response);
  return response.json();
}

async function checkResponse(response:Response):Promise<void> {
  if (!response.ok) {
    let detail: unknown;
    try {detail = (await response.json()).detail;} catch {detail = response.statusText;}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
}

export async function sourceText(projectId:string,resource:Resource,part:string):Promise<string> {
  const response=await fetch(`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}/${part}`);
  await checkResponse(response);
  return response.text();
}

export async function uploadSource(projectId:string,file:File,title:string,replacing?:Resource):Promise<Resource> {
  const body = new FormData();body.append('file',file);body.append('title',title);
  if (replacing)body.append('expected_version',String(replacing.version));
  const path = `/api/projects/${projectId}/resources/` + (replacing ? `${replacing.id}/import` : 'import');
  return responseJson<Resource>(await fetch(path,{method:replacing ? 'PUT':'POST',body}));
}
