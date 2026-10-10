import {FormEvent,useEffect,useRef,useState} from 'react';
import {api,KaggleAccount} from './api';
import {lastProject} from './projectSession';

type Cookie={status:string;expired:boolean;expires_iso:string|null;valid_for_hours:number|null};
type Quota={refresh_at:string|null;gpu?:{used_h:number;remaining_h:number;total_h:number};tpu?:{used_h:number;remaining_h:number;total_h:number}};
type Session={ref:string;title:string;kernel_id:number;kernel_session_id:number;kernel_version_number:number;
  status:string;version_type:string;accelerator:unknown;last_run_time:string|null;
  workbench:{project_id:string;project_name:string;run_id:string;run_title:string;run_state:string;href:string}|null};
type Account=KaggleAccount & {cookie:Cookie|null;quota:Quota|null;sessions:{total_count:number;quota_limits:Record<string,number>;sessions:Session[]}|null;errors:string[]};
type CookieJob={id:string;state:string;accounts:{account:string;status:string;was_expired:boolean|null;message?:string}[]};
type Snapshot={accounts:Account[];cookie_job:CookieJob|null};
const cookieLabels:Record<string,string>={valid:'Còn hiệu lực',expired:'Hết hạn',revoked:'Đã bị thu hồi',identity_mismatch:'Sai account',unverified:'Chưa xác minh'};
const jobLabels:Record<string,string>={pending:'Đang chờ',checking:'Đang kiểm tra',renewing:'Hết hạn · đang tự đăng nhập',
  renewed:'Đã lấy cookie mới',valid:'Cookie còn hiệu lực',unavailable:'Chưa kết nối được',blocked:'Đăng nhập bị chặn',
  needs_manual_verification:'Cần xác minh thủ công',no_credentials:'Thiếu mật khẩu',error:'Chưa hoàn tất',interrupted:'Đã gián đoạn'};
const endpoint='/settings/kaggle-proxy';
const hours=(value:number)=>`${value.toLocaleString('vi-VN',{maximumFractionDigits:2})} giờ`;
function timestamp(value:string|null) {return value ? new Date(value).toLocaleString('vi-VN') : 'Chưa xác minh';}
function accelerator(value:unknown):string {
  if(!value)return 'CPU';
  if(typeof value==='string')return value==='None' || value==='NONE' ? 'CPU' : value;
  if(typeof value==='object') {
    const item=value as Record<string,unknown>;
    const name=item.name || item.type || item.acceleratorType;
    return name ? String(name) : JSON.stringify(value);
  }
  return String(value);
}

export default function SettingsPage() {
  const [data,setData]=useState<Snapshot|null>(null),[selected,setSelected]=useState('');
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
  const [adding,setAdding]=useState(false),[username,setUsername]=useState(''),[token,setToken]=useState(''),[password,setPassword]=useState('');
  const [deleting,setDeleting]=useState<Account|null>(null),[confirmName,setConfirmName]=useState('');
  const alive=useRef(true),inFlight=useRef(false);
  async function load(refresh=false) {
    if(inFlight.current)return;
    inFlight.current=true;
    try {
      const value=await api<Snapshot>(endpoint+(refresh?'?refresh=true':''));
      if(!alive.current)return;
      setData(value);setSelected(current=>value.accounts.some(item=>item.account===current)?current:value.accounts[0]?.account||'');setError('');
    } catch(e) {if(alive.current)setError(e instanceof Error?e.message:String(e));}
    finally {inFlight.current=false;if(alive.current)setLoading(false);}
  }
  useEffect(()=>{alive.current=true;void load();return ()=>{alive.current=false;};},[]);
  const checking=data?.cookie_job?.state==='running';
  useEffect(()=>{
    if(!checking)return;
    const timer=window.setInterval(()=>void load(),1500);
    return ()=>window.clearInterval(timer);
  },[checking]);
  async function action(work:()=>Promise<void>) {
    setBusy(true);setError('');setNotice('');
    try {await work();} catch(e) {setError(e instanceof Error?e.message:String(e));}
    finally {setBusy(false);}
  }
  async function add(event:FormEvent) {
    event.preventDefault();
    await action(async()=>{
      const result=await api<{account:KaggleAccount;cookie_job:CookieJob}>(endpoint+'/accounts','POST',{username,token,password});
      setToken('');setPassword('');setUsername('');setAdding(false);setSelected(result.account.account);
      setNotice('Đã thêm account. Đang tự đăng nhập để lấy cookie.');
      await load();
    });
  }
  const account=data?.accounts.find(item=>item.account===selected);
  const backProject=lastProject();
  return <>
    <aside className="rail settings-rail"><a className="brand" href="/" style={{textDecoration:'none'}}><span className="brand-mark">∿</span><span>AI SCIENTIST<small>LOCAL WORKBENCH</small></span></a>
      <a href={backProject?`/?project=${backProject}`:'/'}>← Quay về Workbench</a>
      <nav className="settings-nav" aria-label="Settings"><a className="active" href="/?page=settings&tab=kaggle-proxy" aria-current="page">Kaggle proxy</a><a href="/?page=settings&tab=multi-agent">Multi-agent</a></nav>
      <div className="rail-footer">Cài đặt dùng chung<br/>cho các project trên máy này.</div>
    </aside>
    <main className="settings-page"><header><div><span className="eyebrow">SETTINGS</span><h1>Kaggle proxy</h1><p className="muted">Quản lý account, quota và các phiên Kaggle.</p></div></header>
      {error && <p role="alert" className="alert error">{error}</p>}{notice && <p role="status" className="alert">{notice}</p>}
      <section className="panel"><div className="panel-head"><h2>Accounts <span className="muted">{data?.accounts.length ?? '—'}</span></h2>
        <div className="actions settings-actions"><button type="button" disabled={busy||checking||loading} onClick={()=>void action(async()=>{await load(true);})}>Làm mới quota / session</button>
          <button type="button" disabled={busy||checking||loading} onClick={()=>void action(async()=>{
            const job=await api<CookieJob>(endpoint+'/check-cookie','POST');
            setData(current=>current?{...current,cookie_job:job}:current);
          })}>{checking?'Đang check cookie…':'Check cookie'}</button>
          <button type="button" className="primary" disabled={busy||checking} onClick={()=>setAdding(value=>!value)}>Thêm account</button></div></div>
        <p className="muted">Check cookie kiểm tra từng account và tự đăng nhập lại khi cookie hết hạn hoặc bị thu hồi.</p>
        {loading && <p role="status">Đang đọc quota và session từ Kaggle…</p>}
        {adding && <form className="stack account-add-form" onSubmit={event=>void add(event)} aria-label="Thêm account Kaggle">
          <h3>Thêm account Kaggle</h3><label>Tên tài khoản Kaggle<input required maxLength={64} pattern="[A-Za-z0-9][A-Za-z0-9_-]*" autoComplete="off" value={username} onChange={e=>setUsername(e.target.value)}/></label>
          <label>Token KGAT<input type="password" required maxLength={1100} autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="KGAT_…"/></label>
          <label>Mật khẩu để auto-login<input type="password" required maxLength={512} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
          <div className="actions"><button className="primary" disabled={busy}>{busy?'Đang xác minh token…':'Lưu và auto-login'}</button><button type="button" disabled={busy} onClick={()=>{setAdding(false);setToken('');setPassword('');}}>Hủy</button></div>
        </form>}
        <div className="settings-table-scroll"><table className="settings-accounts-table"><thead><tr><th>Account</th><th>Cookie</th><th>GPU còn lại</th><th>TPU còn lại</th><th>Session</th><th/></tr></thead><tbody>
          {data?.accounts.map(item=>{const progress=checking?data.cookie_job?.accounts.find(row=>row.account===item.account):null;
            return <tr key={item.account} data-selected={selected===item.account}><td><button type="button" className="run-board-open" onClick={()=>setSelected(item.account)} aria-pressed={selected===item.account}>{item.username}</button>
              {item.default && <small>Mặc định</small>}{!item.configured && <small>Token chưa hợp lệ</small>}</td>
              <td data-label="Cookie"><span className="cookie-state" data-state={item.cookie?.status}>{progress?jobLabels[progress.status]:cookieLabels[item.cookie?.status||'unverified']}</span>
                {item.cookie?.valid_for_hours!=null && item.cookie.valid_for_hours>0 && <small>Còn khoảng {hours(item.cookie.valid_for_hours)}</small>}</td>
              <td data-label="GPU còn lại">{item.quota?.gpu ? <><strong>{hours(item.quota.gpu.remaining_h)}</strong><small>/ {hours(item.quota.gpu.total_h)}</small></>:'Chưa có dữ liệu'}</td>
              <td data-label="TPU còn lại">{item.quota?.tpu ? <><strong>{hours(item.quota.tpu.remaining_h)}</strong><small>/ {hours(item.quota.tpu.total_h)}</small></>:'Chưa có dữ liệu'}</td>
              <td>{item.sessions ? <button type="button" onClick={()=>setSelected(item.account)} aria-label={`Xem session của ${item.username}`}>{item.sessions.total_count} đang chạy</button>:'Chưa xác minh'}</td>
              <td><button type="button" className="danger" disabled={busy||checking} aria-label={`Xóa account ${item.username}`} onClick={()=>{setDeleting(item);setConfirmName('');}}>Xóa</button></td></tr>;
          })}</tbody></table></div>
        {!loading && data?.accounts.length===0 && <p className="empty">Chưa có account. Thêm account để sử dụng proxy.</p>}
      </section>
      {deleting && <section className="panel delete-confirmation" aria-label="Xác nhận xóa account"><h2>Xóa vĩnh viễn {deleting.username}?</h2>
        <p>Token, mật khẩu, cookie và toàn bộ profile trong proxy này sẽ bị xóa. Lịch sử run được giữ. Thao tác này không thể khôi phục.</p>
        <label>Nhập tên account để xác nhận<input autoComplete="off" value={confirmName} onChange={e=>setConfirmName(e.target.value)}/></label>
        <div className="actions"><button type="button" className="danger" disabled={busy||confirmName!==deleting.username} onClick={()=>void action(async()=>{
          await api(endpoint+'/accounts/'+encodeURIComponent(deleting.account),'DELETE');setNotice(`Đã xóa vĩnh viễn ${deleting.username}.`);setDeleting(null);setConfirmName('');await load(true);
        })}>Xóa vĩnh viễn account</button><button type="button" disabled={busy} onClick={()=>setDeleting(null)}>Hủy xóa</button></div></section>}
      {data?.cookie_job && <section className="panel cookie-job" aria-live="polite"><div className="panel-head"><h2>Kết quả check cookie</h2><span className="muted">{checking?'Đang thực hiện':'Đã kết thúc'}</span></div>
        <ul>{data.cookie_job.accounts.map(row=><li key={row.account}><strong>{data.accounts.find(item=>item.account===row.account)?.username||row.account}</strong><span>{jobLabels[row.status]||row.status}{row.was_expired && row.status!=='renewing'?' · cookie cũ hết hạn/không hợp lệ':''}</span>{row.message && <small>{row.message}</small>}</li>)}</ul></section>}
      {account && <section className="panel account-sessions"><div className="panel-head"><h2>Session · {account.username}</h2><span className="muted">{account.sessions?.total_count ?? '—'} đang chạy</span></div>
        <p className="muted">Cập nhật {timestamp(account.observed_at)}{account.quota?.refresh_at?` · Quota làm mới ${timestamp(account.quota.refresh_at)}`:''}</p>
        {account.errors.map((message,index)=><p role="status" className="alert error" key={index}>{message}</p>)}
        {account.sessions?.sessions.map(session=><article className="kaggle-session" key={session.kernel_session_id}>
          <div className="panel-head"><h3>{session.title||session.ref||`Session ${session.kernel_session_id}`}</h3><span className="state-tag">{accelerator(session.accelerator)}</span></div>
          <p className="muted">{session.status} · {session.version_type} · v{session.kernel_version_number} · Session {session.kernel_session_id}</p>
          {session.workbench ? <><p>Project: <strong>{session.workbench.project_name}</strong></p><p>Run: {session.workbench.run_title} · {session.workbench.run_state}</p>
            <a href={session.workbench.href}>Mở run trong Workbench ↗</a></> : <p className="muted">Session ngoài Workbench hoặc chưa xác định được project/run.</p>}
          {session.ref && <p><a href={`https://www.kaggle.com/code/${session.ref}`} target="_blank" rel="noreferrer">Mở notebook Kaggle ↗</a></p>}
        </article>)}
        {account.sessions && !account.sessions.sessions.length && <p className="empty">Account này không có session đang chạy.</p>}
        {!account.sessions && <p className="empty">Chưa đọc được session. Check cookie rồi làm mới trạng thái.</p>}
      </section>}
    </main>
  </>;
}
