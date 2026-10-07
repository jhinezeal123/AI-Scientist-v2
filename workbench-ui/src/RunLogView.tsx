import {useEffect,useRef,useState} from 'react';
import {api} from './api';

const ROW_HEIGHT=22, PAGE_SIZE=80, OVERSCAN=6, CACHE_PAGES=6;
export type LogMetadata={generation:number;total_records:number;total_lines:number;terminal:boolean};
type LogLine={index:number;seq:number;text:string;stream:string};
type LogWindow=LogMetadata & {offset:number;lines:LogLine[];reset:boolean};

export default function RunLogView({projectId,runId,metadata}:{projectId:string;runId:string;metadata:LogMetadata|null}) {
  const viewport=useRef<HTMLDivElement>(null);
  const cache=useRef(new Map<number,LogLine[]>());
  const pending=useRef(new Set<number>());
  const epoch=useRef(0),following=useRef(false);
  const [scrollTop,setScrollTop]=useState(0),[height,setHeight]=useState(360);
  const [expanded,setExpanded]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [,setRevision]=useState(0);
  const generation=metadata?.generation || 1,total=metadata?.total_lines || 0;
  const first=Math.min(total,Math.max(0,Math.floor(scrollTop/ROW_HEIGHT)-OVERSCAN));
  const end=Math.min(total,Math.ceil((scrollTop+height)/ROW_HEIGHT)+OVERSCAN);
  const firstPage=Math.floor(first/PAGE_SIZE)*PAGE_SIZE;
  const lastPage=total ? Math.floor(Math.max(first,end-1)/PAGE_SIZE)*PAGE_SIZE : -1;
  const visiblePages=useRef({firstPage,lastPage});
  visiblePages.current={firstPage,lastPage};

  useEffect(()=>{
    epoch.current++;cache.current.clear();pending.current.clear();following.current=false;
    setScrollTop(0);setError('');setRevision(value=>value+1);
    if(viewport.current)viewport.current.scrollTop=0;
    return ()=>{epoch.current++;};
  },[projectId,runId,generation]);

  useEffect(()=>{
    const element=viewport.current;
    if(!element || !expanded)return;
    const observer=new ResizeObserver(()=>setHeight(element.clientHeight));
    observer.observe(element);setHeight(element.clientHeight);setScrollTop(element.scrollTop);
    return ()=>observer.disconnect();
  },[expanded]);

  useEffect(()=>{
    const element=viewport.current;
    if(element && following.current){
      element.scrollTop=Math.max(0,total*ROW_HEIGHT-element.clientHeight);
      setScrollTop(element.scrollTop);
    }
  },[total,expanded]);

  useEffect(()=>{
    if(!expanded || !total)return;
    const token=epoch.current;
    for(let offset=firstPage;offset<=lastPage;offset+=PAGE_SIZE){
      if((cache.current.get(offset)?.length || 0)>=Math.min(PAGE_SIZE,total-offset) || pending.current.has(offset))continue;
      pending.current.add(offset);
      void api<LogWindow>(`/projects/${projectId}/runs/${runId}/log-window?offset=${offset}&limit=${PAGE_SIZE}&generation=${generation}`)
        .then(page=>{
          if(token!==epoch.current)return;
          if(page.generation!==generation){cache.current.clear();return;}
          cache.current.delete(offset);cache.current.set(offset,page.lines);
          for(const key of cache.current.keys()){
            if(cache.current.size<=CACHE_PAGES)break;
            if(key<visiblePages.current.firstPage || key>visiblePages.current.lastPage)cache.current.delete(key);
          }
          setError('');
        }).catch(e=>{if(token===epoch.current)setError(e instanceof Error ? e.message : String(e));})
        .finally(()=>{
          if(token===epoch.current){pending.current.delete(offset);setRevision(value=>value+1);}
        });
    }
  },[projectId,runId,generation,total,firstPage,lastPage,expanded,retry]);

  function jump(tail:boolean){
    const element=viewport.current;if(!element)return;
    following.current=tail;
    element.scrollTop=tail ? Math.max(0,total*ROW_HEIGHT-element.clientHeight) : 0;
    setScrollTop(element.scrollTop);
  }
  const visibleStart=Math.min(total,Math.floor(scrollTop/ROW_HEIGHT)+1);
  const visibleEnd=Math.min(total,Math.ceil((scrollTop+height)/ROW_HEIGHT));
  return <details className="live-log" open={expanded} onToggle={event=>setExpanded(event.currentTarget.open)}>
    <summary>Log đã lưu · {metadata?.total_records || 0} records · generation {generation}</summary>
    <div className="log-toolbar"><span className="muted">{total ? `Dòng ${visibleStart}–${visibleEnd} / ${total}` : 'Chưa có log'}</span>
      <div className="actions"><button onClick={()=>jump(false)} disabled={!total}>Đầu log</button>
        <button onClick={()=>jump(true)} disabled={!total}>Cuối log</button></div></div>
    {error && <p className="alert error" role="alert">{error} <button onClick={()=>setRetry(value=>value+1)}>Tải lại log</button></p>}
    <div ref={viewport} className="log-viewport" role="region" aria-label="Log Kaggle" tabIndex={0}
      onScroll={event=>{const element=event.currentTarget;setScrollTop(element.scrollTop);
        following.current=total>0 && element.scrollTop+element.clientHeight>=total*ROW_HEIGHT-ROW_HEIGHT;}}>
      {total ? <div className="log-spacer" style={{height:total*ROW_HEIGHT}}>
        <div className="log-window" style={{top:first*ROW_HEIGHT}}>
          {Array.from({length:Math.max(0,end-first)},(_,offset)=>{
            const index=first+offset,line=cache.current.get(Math.floor(index/PAGE_SIZE)*PAGE_SIZE)?.find(item=>item.index===index);
            return <div className="log-line" key={index} data-line={index+1} data-stream={line?.stream} aria-busy={!line}>
              {line ? line.text || '\u00a0' : 'Đang tải…'}</div>;
          })}
        </div></div> : <p className="muted log-empty">Chưa nhận được log. Backend vẫn theo dõi.</p>}
    </div>
  </details>;
}
