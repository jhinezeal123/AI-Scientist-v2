import {ResearchPlan} from './api';

export const emptyResearch = ():ResearchPlan=>({summary:false,report:false,plots:false,writeup:'none',review:false,
  seeds:[],seed_stages:[2,3],reflections:1});

export default function ResearchOptions({value,onChange,disabled=false,readOnly=false}:{value:ResearchPlan;
  onChange?:(plan:ResearchPlan)=>void;disabled?:boolean;readOnly?:boolean}) {
  const update=(part:Partial<ResearchPlan>)=>onChange?.({...value,...part});
  return <fieldset className="output-options" disabled={disabled || readOnly}>
    <legend>Đầu ra tùy chọn</legend>
    <div className="output-option-grid">
      {(['summary','report','plots'] as const).map(key=><label className="check" key={key}>
        <input type="checkbox" checked={value[key]} onChange={e=>update({[key]:e.target.checked})}/>
        <span>{key==='summary' ? 'Summary' : key==='report' ? 'Report' : 'Plots'}</span></label>)}
      <label className="check"><input type="checkbox" checked={value.writeup!=='none'}
        onChange={e=>update({writeup:e.target.checked ? 'icbinb' : 'none'})}/><span>PDF</span></label>
      <label className="check"><input type="checkbox" checked={value.review}
        onChange={e=>update({review:e.target.checked})}/><span>Review</span></label>
    </div>
    {value.writeup!=='none' && <label>Mẫu PDF<select value={value.writeup}
      onChange={e=>update({writeup:e.target.value as 'icbinb'|'normal'})}>
      <option value="icbinb">ICBINB · 4 trang</option><option value="normal">ICML · 8 trang</option></select></label>}
    {!readOnly && <small className="muted">Chỉ tạo các đầu ra bạn chọn. Lựa chọn được ghim cùng proposal khi duyệt.</small>}
  </fieldset>;
}
