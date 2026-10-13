import {KaggleAccount} from './api';
import {RunConfiguration} from './projectConfiguration';
import ExperimentSettings from './ExperimentSettings';

export const readinessLabels:Record<string,string>={verified_idle:'Đã kiểm tra idle',unverified:'Chưa kiểm tra',
  busy:'Đang có phiên chạy',needs_login:'Cần đăng nhập lại',unavailable:'Chưa kết nối được'};

export default function RunExecutionFields({value,accounts,onChange,allowSearch=true}:{value:RunConfiguration;
  accounts:KaggleAccount[];onChange:(part:Partial<RunConfiguration>)=>void;allowSearch?:boolean}){
  return <div className="stack run-execution-fields">
    <div className="team-create"><label>Account Kaggle<select value={value.account} onChange={e=>onChange({account:e.target.value})}>
      <option value="">Chọn account</option>{accounts.map(account=><option key={account.account} value={account.account} disabled={!account.configured}>
        {account.username} · {readinessLabels[account.readiness]||account.readiness}</option>)}</select></label>
      <label>Accelerator<select value={value.accelerator} onChange={e=>onChange({accelerator:e.target.value})}>
        <option value="cpu">CPU</option><option value="NvidiaT4">GPU · T4 x2</option>
        <option value="TpuV5E8">TPU · v5e-8</option><option value="TpuV6E8">TPU · v6e-8</option></select></label>
      <label>Thời hạn phiên (phút)<input type="number" min={3} max={720} step={1} value={value.ttl_seconds/60}
        onChange={e=>onChange({ttl_seconds:Number(e.target.value)*60})}/></label></div>
    <details><summary>Budget và cấu hình nâng cao</summary><div className="stack">
      <div className="team-create"><label>Budget thực thi (giây)<input type="number" min={1} max={43080} value={value.execution_seconds}
        onChange={e=>onChange({execution_seconds:Number(e.target.value)})}/></label>
        <label>Giới hạn output (bytes)<input type="number" min={1} max={10000000} value={value.output_bytes}
          onChange={e=>onChange({output_bytes:Number(e.target.value)})}/></label></div>
      <p className="muted">Budget thực thi phải nằm trong thời hạn phiên, chừa ít nhất 2 phút để thu kết quả.</p>
      {allowSearch&&<ExperimentSettings spec={value} onChange={onChange}/>}</div></details>
  </div>;
}
