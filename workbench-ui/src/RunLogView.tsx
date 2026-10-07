export type LogEntry = {seq:number;text:string;stream:string};

export default function RunLogView({entries,generation}:{entries:LogEntry[];generation:number}) {
  return <details className="live-log" open><summary>Log đã lưu · {entries.length} records · generation {generation}</summary>
    {entries.length ? <pre aria-label="Log Kaggle">{entries.map(entry=><span key={entry.seq} data-stream={entry.stream}>{entry.text}{entry.text.endsWith('\n') ? '' : '\n'}</span>)}</pre> : <p className="muted">Chưa nhận được log. Bạn có thể chuyển tab; backend vẫn theo dõi.</p>}
  </details>;
}
