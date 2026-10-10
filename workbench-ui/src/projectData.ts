import {api, Benchmark, History, Idea, Proposal, Resource} from './api';

/** Read saved project data without starting an agent or a Kaggle session. */
export function loadProjectData(projectId:string) {
  return Promise.all([
    api<Resource[]>(`/projects/${projectId}/resources`),
    api<Idea[]>(`/projects/${projectId}/ideas?include_deleted=true`),
    api<History>(`/projects/${projectId}/history?include_deleted=true`),
    api<Proposal[]>(`/projects/${projectId}/proposals`),
    api<Benchmark[]>(`/projects/${projectId}/benchmarks`),
  ]);
}
