import type {ModelCapabilities} from './contracts';
export type CustomModelDefinition={slug:string;name:string;capabilities:ModelCapabilities|null};
export function normalizeCustomModelSlug(model:string|null|undefined):string|null{return typeof model==='string'?model.trim()||null:null;}
export function createModelCapabilities(input:ModelCapabilities):ModelCapabilities{return structuredClone(input);}
export function readCustomModelEntries(value:unknown):CustomModelDefinition[]{
  if(!Array.isArray(value))return [];
  const seen=new Set<string>(),entries:CustomModelDefinition[]=[];
  for(const raw of value){
    const row=typeof raw==='string'?{slug:raw}:raw&&typeof raw==='object'?raw:null;
    const slug=normalizeCustomModelSlug(row?.slug);if(!slug||seen.has(slug))continue;seen.add(slug);
    entries.push({slug,name:normalizeCustomModelSlug(row.name)||slug,capabilities:row.capabilities??null});
  }return entries;
}
export const toCustomModelSetting=(entry:CustomModelDefinition)=>entry;
