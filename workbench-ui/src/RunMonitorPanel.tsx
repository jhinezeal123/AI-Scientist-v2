import {useEffect,useState} from 'react';
import {api} from './api';

type Delta={run_state:string;generation:number;entries:{seq:number;text:string;stream:string}[];next_cursor:string;
  has_more:boolean;reset:boolean;gap:boolean;terminal:boolean;
  error:string|null;
  observation:{identity:{status:string};observed_at:string;source:string;complete:boolean}|null};

export default function RunMonitorPanel({projectId,runId,onObserved}:{projectId:string;runId:string;onObserved:(state:string)=>void}) {
  const [data,setData]=useState<Delta|null>(null);
  const [entries,setEntries]=useState<Delta['entries']>([]);
  const [error,setError]=useState('');
  useEffect(() => {
    let cancelled=false;let cursor:string|undefined;let generation:number|undefined;let timer:number;
    setData(null);setEntries([]);setError('');
    async function poll() {
      try {
        let page:Delta;
        do {
          page=await api<Delta>(`/projects/${projectId}/runs/${runId}/logs${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`);
          if (cancelled)return;
          const changed=generation!==undefined && generation!==page.generation;
          generation=page.generation;cursor=page.next_cursor;
          const received=page;
          setEntries(old => {
            const base=changed || received.reset ? [] : old;
            const last=base.length ? base[base.length-1].seq : 0;
            return [...base,...received.entries.filter(entry => entry.seq>last)];
          });
          setData(page);setError('');
          onObserved(page.run_state);
        } while (page.has_more);
        if (!page.terminal)timer=window.setTimeout(poll,2000);
      } catch(e) {
        if (!cancelled) {setError(e instanceof Error ? e.message : String(e));timer=window.setTimeout(poll,2000);}
      }
    }
    void poll();
    return () => {cancelled=true;window.clearTimeout(timer);};
  },[projectId,runId,onObserved]);
  return <div className="context monitor-panel"><div className="panel-head"><h3>Theo dõi Kaggle</h3>
    <span className="state-tag">{data?.terminal ? 'Đã kết thúc' : data?.observation ? 'Theo dõi nền' : 'Đang chờ quan sát'}</span></div>
    {data?.observation && <p className="muted">{data.observation.identity.status} · Quan sát lúc {new Date(data.observation.observed_at).toLocaleTimeString('vi-VN')}</p>}
    {(error || data?.error) && <p className="alert error" role="alert">{error || data?.error}</p>}
    {data?.gap && <p className="alert error">Nguồn log bị cắt hoặc đổi. Đã lưu generation mới; đang chờ đối soát log terminal.</p>}
    <details className="live-log" open><summary>Log đã lưu · {entries.length} records · generation {data?.generation || 1}</summary>
      {entries.length ? <pre aria-label="Log Kaggle">{entries.map(entry=><span key={entry.seq} data-stream={entry.stream}>{entry.text}{entry.text.endsWith('\n') ? '' : '\n'}</span>)}</pre> : <p className="muted">Chưa nhận được log. Bạn có thể chuyển tab; backend vẫn theo dõi.</p>}
    </details>
  </div>;
}
