import {Benchmark,BenchmarkDefinition,RunMode} from './api';

export const emptyBenchmark=():BenchmarkDefinition=>({metric:{name:'',direction:'minimize',definition:''},test_split:'',train_split:null});

export default function BenchmarkFields({mode,benchmarks,benchmarkId,definition,disabled,onSelect,onDefinition}:{
  mode:RunMode;benchmarks:Benchmark[];benchmarkId:string;definition:BenchmarkDefinition;disabled:boolean;
  onSelect:(id:string)=>void;onDefinition:(value:BenchmarkDefinition)=>void;
}) {
  if(mode==='etc')return null;
  if(mode==='training_research')return <>
    <label>Benchmark bắt buộc<select required value={benchmarkId} disabled={disabled} onChange={e=>onSelect(e.target.value)}>
      <option value="">Chọn benchmark đã hoàn tất</option>
      {benchmarks.map(item=><option key={item.id} value={item.id}>{item.title} · dataset v{item.dataset.version}</option>)}
    </select></label>
    {!benchmarks.length && <p className="muted">Chọn “Tạo benchmark mới” để chuẩn bị tập test và metric trước.</p>}
    {benchmarks.find(item=>item.id===benchmarkId) && <div className="context">
      <strong>{benchmarks.find(item=>item.id===benchmarkId)!.definition.metric.name}</strong>
      <p>{benchmarks.find(item=>item.id===benchmarkId)!.definition.metric.definition}</p>
      <small>Các run cùng benchmark được so sánh bằng MLflow, kể cả khác số steps. Tập train có thể không có.</small>
    </div>}
  </>;
  return <fieldset className="stack"><legend>Định nghĩa benchmark</legend>
    <label>Tên metric<input required maxLength={100} value={definition.metric.name} disabled={disabled}
      placeholder="accuracy, latency_ms, peak_memory_mb…"
      onChange={e=>onDefinition({...definition,metric:{...definition.metric,name:e.target.value}})}/></label>
    <label>Chiều tối ưu<select value={definition.metric.direction} disabled={disabled}
      onChange={e=>onDefinition({...definition,metric:{...definition.metric,direction:e.target.value as 'minimize'|'maximize'}})}>
      <option value="minimize">Càng thấp càng tốt</option><option value="maximize">Càng cao càng tốt</option>
    </select></label>
    <label>Cách tính metric<textarea required rows={3} maxLength={20000} value={definition.metric.definition} disabled={disabled}
      placeholder="Đơn vị, cách đo và tổng hợp; ví dụ trung vị latency sau 10 lượt warmup…"
      onChange={e=>onDefinition({...definition,metric:{...definition.metric,definition:e.target.value}})}/></label>
    <label>Tập test và cách chia — bắt buộc<textarea required rows={4} maxLength={20000} value={definition.test_split} disabled={disabled}
      placeholder="Nguồn dữ liệu, mẫu được chọn, quy tắc chia/group/seed, hoặc sử dụng toàn bộ dữ liệu làm test…"
      onChange={e=>onDefinition({...definition,test_split:e.target.value})}/></label>
    <label>Tập train và cách chia — tùy chọn<textarea rows={3} maxLength={20000} value={definition.train_split||''} disabled={disabled}
      placeholder="Để trống khi nghiên cứu inference, memory, cache không cần training."
      onChange={e=>onDefinition({...definition,train_split:e.target.value||null})}/></label>
    <small className="muted">Benchmark chạy trên Kaggle và tạo dataset public chứa tập test cùng evaluator. Kết quả là link dataset. Đổi phép đo bằng cách tạo benchmark mới.</small>
  </fieldset>;
}
