import {RunConfiguration} from './projectConfiguration';

export default function ExperimentSettings({spec,onChange}:{spec:Pick<RunConfiguration,'search'>;onChange:(value:Pick<RunConfiguration,'search'>)=>void}){
  const search=spec.search;
  const set=(value:Partial<typeof search>)=>onChange({search:{...search,...value}});
  return <fieldset className="output-options experiment-settings"><legend>Experiment manager</legend>
    <label className="check"><input type="checkbox" checked={search.enabled} onChange={e=>set({enabled:e.target.checked})}/>Tìm kiếm thí nghiệm · Draft → Tuning → Research → Ablation</label>
    <p className="muted">{search.enabled?'Agent phát triển baseline, thử cấu hình, cải tiến phương pháp và làm ablation. Mỗi bước được hiển thị riêng trên n8n.':'Đang chạy một thí nghiệm theo proposal. Bật để dùng bốn giai đoạn tìm kiếm của upstream.'}</p>
    {search.enabled&&<>
      <div className="team-create"><label>Nhánh chạy song song<input type="number" min={1} max={4} value={search.num_workers} onChange={e=>set({num_workers:Number(e.target.value)})}/></label>
        <label>Baseline khởi đầu tối đa<input type="number" min={1} value={search.num_drafts} onChange={e=>set({num_drafts:Number(e.target.value)})}/></label></div>
      <p className="muted">Mỗi nhánh có thư mục, shell SSH và phiên agent riêng. Các nhánh dùng chung CPU/GPU của một phiên Kaggle và cùng giới hạn lượt agent, thời gian, dữ liệu đã duyệt.</p>
      <div className="team-create">{['Draft','Tuning','Research','Ablation'].map((label,i)=><label key={label}>{label} · số node tối đa<input type="number" min={1} value={search.stage_iterations[i]} onChange={e=>set({stage_iterations:search.stage_iterations.map((n,j)=>i===j?Number(e.target.value):n)})}/></label>)}</div>
      <label className="check"><input type="checkbox" checked={search.scale_experiments} onChange={e=>set({scale_experiments:e.target.checked})}/>Cho phép tăng quy mô thí nghiệm trong stage Research</label>
      <p className="muted">Agent có thể tăng số epoch, kích thước model hoặc lượng dữ liệu trong nguồn đã chọn. Benchmark, split và budget đã duyệt vẫn được giữ.</p>
    </>}
  </fieldset>;
}
