export default function ArtifactLinks({projectId,runId,names,previews=false}:{projectId:string;runId:string;names:string[];previews?:boolean}) {
  return <div className="stack">{names.map(name=>{
    const href=`/api/projects/${projectId}/runs/${runId}/artifacts/${name.split('/').map(encodeURIComponent).join('/')}`;
    const previewable=/\.(txt|md|csv|json|py|ipynb|png|jpe?g|gif|webp|pdf)$/i.test(name);
    return previews ? <div className="output-file" key={name}><strong>{name}</strong><div className="actions">
      {previewable && <a href={`${href}?download=false`} target="_blank" rel="noreferrer">Mở ↗</a>}
      <a href={href} download>Tải file</a></div></div>
      : <a key={name} href={href} target="_blank" rel="noreferrer">{name} ↗</a>;
  })}</div>;
}
