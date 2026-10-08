import {RunMode} from './api';

export default function ModeFields({mode,desiredOutput,disabled,onMode,onOutput}:{
  mode:RunMode;desiredOutput:string;disabled:boolean;onMode:(mode:RunMode)=>void;onOutput:(value:string)=>void;
}) {
  return <>
    <label>Mode của idea<select value={mode} disabled={disabled} onChange={event=>onMode(event.target.value as RunMode)}>
      <option value="training_research">Training/Research</option><option value="etc">Etc</option>
    </select></label>
    {mode==='etc' && <>
      <label>Đầu ra mong muốn<textarea rows={4} maxLength={20000} value={desiredOutput} disabled={disabled}
        placeholder="Mô tả kết quả bạn cần nhận: nội dung, bảng, file, ảnh…"
        onChange={event=>onOutput(event.target.value)}/></label>
      <small className="muted">Bắt buộc trước khi lập hoặc duyệt proposal. Có thể lưu bản nháp khi chưa nhập. Working Etc được triển khai ở M2-02.</small>
    </>}
  </>;
}
