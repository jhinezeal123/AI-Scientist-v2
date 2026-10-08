import {useState} from 'react';
import {Resource,sourceText} from './api';

export default function ImportedSource({projectId,resource}:{projectId:string;resource:Resource}) {
  const [view,setView]=useState<{label:string;text:string}|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const attachment=resource.attachment;
  if (!attachment)return null;
  async function read(part:string,label:string) {
    setLoading(true);setError('');
    try {setView({label,text:await sourceText(projectId,resource,part)});}
    catch(error) {setError(error instanceof Error ? error.message : String(error));}
    finally {setLoading(false);}
  }
  return <div className="stack"><a href={`/api/projects/${projectId}/library/${resource.id}/versions/${resource.version}/original`}>Tải bản gốc · {attachment.filename}</a>
    <code className="source-id">{attachment.original_file_path}</code>
    {attachment.page_count !== null ? <div><p className="muted">{attachment.text_pages}/{attachment.page_count} trang có text</p>
      {attachment.processed_pages > 0 && <details><summary>Text theo trang</summary><div className="page-picker">
        {Array.from({length:attachment.processed_pages},(_,index)=><button type="button" key={index} disabled={loading}
          onClick={()=>void read(`pages/${index+1}`,`Trang ${index+1}`)}>Trang {index+1}</button>)}
      </div></details>}</div>
      : ['extracted','partial','no_text'].includes(resource.status) && <button type="button" disabled={loading} onClick={()=>void read('text','Text đã trích')}>Xem text đã trích</button>}
    {loading && <small role="status">Đang đọc text…</small>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {view && <div><div className="panel-head"><strong>{view.label} · v{resource.version}</strong><button type="button" onClick={()=>setView(null)}>Đóng text</button></div>
      <pre aria-label={view.label}>{view.text}</pre></div>}
    {attachment.issues.map((issue,index)=><p className="muted" key={index}>{issue}</p>)}
  </div>;
}
