import type {HarnessSpec,ModelCatalog} from './agentPresets';
import {sortModelsForProviderInstance} from './vendor/t3code/modelOrdering';

export type ModelPreferences={hidden:string[];favorites:string[];order:string[]};
export const emptyModelPreferences:ModelPreferences={hidden:[],favorites:[],order:[]};

export function providerModelOptions(spec:HarnessSpec,catalog?:ModelCatalog,preferences=emptyModelPreferences,currentModel:string|null=null){
  const models=[...(catalog?.models??[]).filter(model=>!model.isCustom),...(spec.custom_models??[]).map(model=>({...model,isCustom:true}))];
  const unique=models.filter((model,index)=>models.findIndex(row=>row.slug===model.slug)===index);
  return sortModelsForProviderInstance(unique.filter(model=>!preferences.hidden.includes(model.slug)||model.slug===currentModel),{
    modelOrder:preferences.order,favoriteModels:preferences.favorites,groupFavorites:true,
  });
}
