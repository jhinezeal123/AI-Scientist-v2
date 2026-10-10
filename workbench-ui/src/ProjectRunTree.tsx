import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {History} from './api';

type Run=History['runs'][number];
const W=242,H=92,GAP=28,LEVEL=150;
const stateLabels:Record<string,string>={APPROVED:'Sẵn sàng Working',WORKING:'Đang Working',STARTING:'Đang mở phiên',
  STOPPING:'Đang dừng',COMPLETED:'Hoàn tất',FAILED:'Có lỗi',CANCELLED:'Đã dừng',UNKNOWN:'Cần đối soát',
  REMOTE_SUCCEEDED:'Hoàn tất',REMOTE_FAILED:'Có lỗi',PREFLIGHT:'Sẵn sàng Working'};

function layout(runs:Run[]) {
  const byId=new Map(runs.map(run=>[run.id,run]));
  const children=new Map<string,Run[]>();
  const roots:Run[]=[];
  for (const run of [...runs].reverse()) {
    if (run.parent_run_id && run.parent_run_id!==run.id && byId.has(run.parent_run_id)) {
      const group=children.get(run.parent_run_id) || [];group.push(run);children.set(run.parent_run_id,group);
    } else roots.push(run);
  }
  const widths=new Map<string,number>(),seen=new Set<string>();
  function measure(run:Run,ancestors=new Set<string>()):number {
    if (ancestors.has(run.id))return W;
    const next=new Set(ancestors);next.add(run.id);
    const nodes=children.get(run.id) || [];
    const width=Math.max(W,nodes.reduce((sum,child)=>sum+measure(child,next),0)+Math.max(0,nodes.length-1)*GAP);
    widths.set(run.id,width);return width;
  }
  roots.forEach(root=>measure(root));
  const positions=new Map<string,{run:Run;x:number;y:number}>();
  function place(run:Run,left:number,depth:number) {
    if (seen.has(run.id))return;seen.add(run.id);
    const width=widths.get(run.id) || W;
    positions.set(run.id,{run,x:left+(width-W)/2,y:depth*LEVEL+35});
    let cursor=left;
    for (const child of children.get(run.id) || []) {place(child,cursor,depth+1);cursor+=(widths.get(child.id) || W)+GAP;}
  }
  let cursor=35;
  roots.forEach(root=>{place(root,cursor,1);cursor+=(widths.get(root.id) || W)+GAP;});
  // Corrupt legacy links cannot hide a run or recurse forever.
  runs.filter(run=>!seen.has(run.id)).forEach(run=>{positions.set(run.id,{run,x:cursor,y:LEVEL+35});cursor+=W+GAP;});
  return {nodes:[...positions.values()],edges:[...positions.values()].flatMap(node=>{
    const parent=node.run.parent_run_id ? positions.get(node.run.parent_run_id) : undefined;
    return parent && parent!==node ? [{from:parent,to:node}] : [];
  }),width:Math.max(300,cursor),height:Math.max(160,...[...positions.values()].map(node=>node.y+H+35))};
}

export default function ProjectRunTree({runs,selectedId,onSelect,large=false}:{runs:Run[];selectedId:string|null;
  onSelect:(id:string)=>void;large?:boolean}) {
  const graph=useMemo(()=>layout(runs),[runs]);
  const svg=useRef<SVGSVGElement>(null);
  const [view,setView]=useState({x:20,y:20,k:1});
  const drag=useRef<{x:number;y:number;vx:number;vy:number;moved:boolean;node:string|null}|null>(null);
  const fit=useCallback(()=>{
    const box=svg.current?.getBoundingClientRect();if (!box)return;
    const k=Math.min(1.1,Math.max(.001,Math.min((box.width-30)/graph.width,(box.height-30)/graph.height)));
    setView({k,x:(box.width-graph.width*k)/2,y:(box.height-graph.height*k)/2});
  },[graph.width,graph.height]);
  useEffect(()=>{
    const element=svg.current;if (!element)return;
    // The sidebar and responsive grid may resize after the first data load.
    // Refit on geometry changes, while ordinary status polling preserves pan/zoom.
    fit();
    const observer=new ResizeObserver(fit);
    observer.observe(element);
    return ()=>observer.disconnect();
  },[fit]);
  useEffect(()=>{
    const element=svg.current;if (!element)return;
    const wheel=(event:WheelEvent)=>{
      event.preventDefault();const box=element.getBoundingClientRect();
      const x=event.clientX-box.left,y=event.clientY-box.top;
      setView(old=>{const k=Math.min(3,Math.max(.001,old.k*Math.exp(-event.deltaY*.0015)));
        return {k,x:x-(x-old.x)*k/old.k,y:y-(y-old.y)*k/old.k};});
    };
    element.addEventListener('wheel',wheel,{passive:false});
    return ()=>element.removeEventListener('wheel',wheel);
  },[]);
  return <div className={`project-run-tree ${large ? 'large' : ''}`}>
    <div className="tree-toolbar"><span>Kéo để di chuyển · cuộn để zoom</span>
      <div className="actions"><button type="button" onClick={()=>setView(old=>({...old,k:Math.min(3,old.k*1.2)}))} aria-label="Phóng to cây">+</button>
        <button type="button" onClick={()=>setView(old=>({...old,k:Math.max(.001,old.k/1.2)}))} aria-label="Thu nhỏ cây">−</button>
        <button type="button" onClick={fit}>Vừa khung</button></div></div>
    <svg ref={svg} role="group" aria-label="Cây run của project" onPointerDown={event=>{
      if (event.button!==0)return;const target=event.target as Element;
      drag.current={x:event.clientX,y:event.clientY,vx:view.x,vy:view.y,moved:false,node:target.closest('[data-run-id]')?.getAttribute('data-run-id') || null};
      event.currentTarget.setPointerCapture(event.pointerId);
    }} onPointerMove={event=>{
      const start=drag.current;if (!start)return;
      const dx=event.clientX-start.x,dy=event.clientY-start.y;
      if (Math.hypot(dx,dy)>5)start.moved=true;
      if (start.moved)setView(old=>({...old,x:start.vx+dx,y:start.vy+dy}));
    }} onPointerUp={event=>{
      const start=drag.current;drag.current=null;
      if (event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
      if (start && !start.moved && start.node)onSelect(start.node);
    }} onPointerCancel={()=>{drag.current=null;}}>
      <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
        {graph.nodes.filter(node=>!node.run.parent_run_id || !runs.some(run=>run.id===node.run.parent_run_id)).map(node=><path
          key={'project:'+node.run.id} className="run-tree-edge"
          d={`M${graph.width/2},85 C${graph.width/2},130 ${node.x+W/2},140 ${node.x+W/2},${node.y}`}/>)}
        <g className="project-tree-root" transform={`translate(${graph.width/2-70},35)`}><rect width={140} height={50} rx={25}/>
          <text x={70} y={31} textAnchor="middle">Project</text></g>
        {graph.edges.map(({from,to})=><path key={`${from.run.id}:${to.run.id}`} className="run-tree-edge"
          d={`M${from.x+W/2},${from.y+H} C${from.x+W/2},${from.y+H+30} ${to.x+W/2},${to.y-30} ${to.x+W/2},${to.y}`}/>)}
        {graph.nodes.map(({run,x,y})=><g key={run.id} transform={`translate(${x},${y})`} data-run-id={run.id}
          className={`run-tree-node ${run.id===selectedId ? 'selected' : ''}`} data-mode={run.mode} role="button" tabIndex={0}
          aria-label={`${run.title || 'Run '+run.id.slice(0,8)} · ${stateLabels[run.state] || run.state}`}
          aria-pressed={run.id===selectedId} onKeyDown={event=>{if (event.key==='Enter' || event.key===' '){event.preventDefault();onSelect(run.id);}}}>
          <title>{run.title || run.purpose || run.id}{'\n'}{run.id}</title>
          <rect width={W} height={H} rx={12}/><rect className="node-mode-stripe" width={5} height={H-20} x={0} y={10} rx={2}/>
          <text className="node-title" x={16} y={27}>{(run.title || 'Run '+run.id.slice(0,8)).slice(0,28)}{(run.title?.length || 0)>28 ? '…' : ''}</text>
          <text className="node-kind" x={16} y={49}>{run.mode==='benchmark' ? 'Benchmark' : run.mode==='etc' ? 'Etc' : run.parent_run_id ? 'Improve' : 'Draft'}
            {run.tags?.length ? ' · '+run.tags.join(' / ') : ''}</text>
          <circle className="node-state-dot" data-state={run.state} cx={20} cy={72} r={4}/>
          <text className="node-status" x={32} y={77}>{run.deleted_at ? 'Đã xóa trước đây' : stateLabels[run.state] || run.state}</text>
        </g>)}
      </g>
    </svg>
  </div>;
}
