import {FormEvent,useState} from 'react';
import {Resource,uploadSource} from './api';

type Props={projectId:string;busy:boolean;replacing:Resource|null;onCancel:()=>void;
  onUpload:(work:()=>Promise<void>)=>Promise<void>;onSaved:(resource:Resource)=>void};

export default function FileImport({projectId,busy,replacing,onCancel,onUpload,onSaved}:Props) {
  const [file,setFile]=useState<File|null>(null);
  const [title,setTitle]=useState(replacing?.title || '');
  const [reset,setReset]=useState(0);
  function submit(event:FormEvent) {
    event.preventDefault();if (!file)return;
    void onUpload(async()=>{
      const source=await uploadSource(projectId,file,title,replacing || undefined);
      setFile(null);setTitle('');setReset(value=>value+1);onSaved(source);
    });
  }
  return <div className="context"><h3>{replacing ? `Thay file · ${replacing.title} · v${replacing.version}` : 'Nhập PDF / file'}</h3>
    <form className="stack" onSubmit={submit}>
      <label>Tiêu đề tài liệu<input maxLength={240} value={title} placeholder="Để trống để dùng tên file" onChange={event=>setTitle(event.target.value)}/></label>
      <label>Chọn tài liệu<input key={reset} type="file" required disabled={busy} onChange={event=>setFile(event.target.files?.[0] || null)}/></label>
      <small className="muted">Tối đa 25 MB/file. PDF có text được trích theo trang; PDF scan, file khóa hoặc lỗi được ghi rõ. Bản gốc được giữ theo phiên bản.</small>
      <div className="actions"><button className="primary" disabled={busy || !file}>{replacing ? 'Lưu phiên bản file mới' : 'Nhập tài liệu'}</button>
        {replacing && <button type="button" disabled={busy} onClick={onCancel}>Hủy thay file</button>}</div>
    </form>
  </div>;
}
