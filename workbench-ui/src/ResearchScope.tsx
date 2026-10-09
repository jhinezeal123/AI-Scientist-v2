import {ResearchPlan, ResearchPipeline} from './api';

const parts:Record<string,string>={tree:'Cây bốn giai đoạn',multi_seed:'Đánh giá nhiều seed',
  summary:'Summary thí nghiệm',report:'Report kỹ thuật',plots:'Tổng hợp figures',writeup:'Bài PDF',review:'Review văn bản'};
const statuses:Record<string,string>={pending:'Chưa chạy',running:'Đang chạy',completed:'Hoàn tất',
  failed:'Có lỗi',interrupted:'Bị gián đoạn',blocked:'Thiếu đầu vào',not_requested:'Không yêu cầu'};

export default function ResearchScope({plan,pipeline,projectId,runId}:{plan:ResearchPlan;pipeline?:ResearchPipeline|null;projectId?:string;runId?:string}) {
  return <div className="research-scope">
    <p>Summary: {plan.summary ? 'có' : 'không'} · Report: {plan.report ? 'có' : 'không'} · Figures: {plan.plots ? 'có' : 'không'}</p>
    <p>PDF: {plan.writeup==='none' ? 'không yêu cầu' : plan.writeup==='icbinb' ? 'ICBINB · mục tiêu 4 trang' : 'ICML · mục tiêu 8 trang'} · Review văn bản: {plan.review ? 'có' : 'không'}</p>
    <p>{plan.seeds.length ? `Seed training: ${plan.seeds.join(', ')} · Stage ${plan.seed_stages.join(', ')}. Giữ nguyên split; không chọn mô hình theo seed tốt nhất.` : 'Không chạy thêm seed.'}</p>
    {(plan.plots || plan.writeup!=='none') && <p>Số lượt sửa figures/bài: {plan.reflections}</p>}
    {pipeline && <ul className="research-progress" aria-label="Trạng thái pipeline Research">
      {Object.entries(pipeline.components).map(([name,item])=>{
        const artifact=item.artifacts.find(path=>path.endsWith('.html')) || item.artifacts[0];
        const href=projectId && runId && artifact ? `/api/projects/${projectId}/runs/${runId}/artifacts/${artifact.split('/').map(encodeURIComponent).join('/')}?download=false` : null;
        return <li key={name}><div className="panel-head"><strong>{parts[name] || name}</strong>
          <span className="research-status" data-status={item.status}>{statuses[item.status] || item.status}</span></div>
          {item.reason && <small className="muted">{item.reason}</small>}
          {href && <a href={href} target="_blank" rel="noreferrer">Mở kết quả ↗</a>}
        </li>;
      })}
    </ul>}
  </div>;
}
