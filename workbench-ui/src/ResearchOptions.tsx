import {ResearchPlan} from './api';

export const emptyResearch = ():ResearchPlan=>({summary:false,report:false,plots:false,writeup:'none',review:false,
  literature:false,literature_rounds:5,citations:false,citation_rounds:20,vlm:false,seeds:[],seed_stages:[2,3],reflections:1});

export default function ResearchOptions({value,onChange,disabled=false,readOnly=false}:{value:ResearchPlan;
  onChange?:(plan:ResearchPlan)=>void;disabled?:boolean;readOnly?:boolean}) {
  const update=(part:Partial<ResearchPlan>)=>onChange?.({...value,...part});
  return <fieldset className="output-options" disabled={disabled || readOnly}>
    <legend>Đầu ra tùy chọn</legend>
    <div className="output-option-grid">
      <label className="check"><input type="checkbox" checked={value.literature} onChange={e=>update({literature:e.target.checked})}/><span>Literature / novelty</span></label>
      {(['summary','report','plots'] as const).map(key=><label className="check" key={key}>
        <input type="checkbox" checked={value[key]} onChange={e=>update({[key]:e.target.checked})}/>
        <span>{key==='summary' ? 'Summary' : key==='report' ? 'Report' : 'Plots'}</span></label>)}
      <label className="check"><input type="checkbox" checked={value.writeup!=='none'}
        onChange={e=>update({writeup:e.target.checked ? 'icbinb' : 'none'})}/><span>PDF</span></label>
      <label className="check"><input type="checkbox" checked={value.review}
        onChange={e=>update({review:e.target.checked})}/><span>Review</span></label>
      <label className="check"><input type="checkbox" checked={!!value.citations} onChange={e=>update({citations:e.target.checked})}/><span>Thu thập citation</span></label>
      <label className="check"><input type="checkbox" checked={!!value.vlm} onChange={e=>update({vlm:e.target.checked})}/><span>VLM đánh giá hình</span></label>
    </div>
    {value.citations && <label>Số vòng citation tối đa<input type="number" min={1} max={40} value={value.citation_rounds||20} onChange={e=>update({citation_rounds:Number(e.target.value)})}/></label>}
    {value.writeup!=='none' && <label>Mẫu PDF<select value={value.writeup}
      onChange={e=>update({writeup:e.target.value as 'icbinb'|'normal'})}>
      <option value="icbinb">ICBINB · 4 trang</option><option value="normal">ICML · 8 trang</option></select></label>}
    {value.literature&&<label>Số vòng literature / novelty tối đa<input type="number" min={2} max={20} value={value.literature_rounds} onChange={e=>update({literature_rounds:Number(e.target.value)})}/></label>}
    {(value.plots||value.writeup!=='none')&&<label>Số vòng sửa figures / bài<input type="number" min={0} max={10} value={value.reflections} onChange={e=>update({reflections:Number(e.target.value)})}/></label>}
    {!readOnly && <small className="muted">Chỉ tạo các đầu ra bạn chọn. Lựa chọn được ghim cùng proposal khi duyệt.</small>}
  </fieldset>;
}
