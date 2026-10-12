import {useEffect,useState} from 'react';
import {readSlack,saveSlack,sendSlack} from './slackApi';
import useAgentAction from './useAgentAction';

export default function SlackSettings({admin}:{admin:boolean}){
  const [slack,setSlack]=useState({enabled:false,channel:''}),[text,setText]=useState('');
  const {busy,error,notice,setNotice,action}=useAgentAction();
  useEffect(()=>{let stopped=false;if(admin)void action(async()=>{
    const config=await readSlack();if(!stopped)setSlack({enabled:config.enabled,channel:config.channel||''});
  });return()=>{stopped=true;};},[admin,action]);
  if(!admin)return null;
  return <>{error&&<p role="alert" className="alert error">{error}</p>}{notice&&<p role="status" className="alert">{notice}</p>}
    <section className="panel"><h2>Slack</h2><p className="muted">Token backend: AI_SCIENTIST_SLACK_TOKEN. Chỉ gửi khi bạn bấm Gửi.</p>
      <label><input type="checkbox" checked={slack.enabled} onChange={e=>setSlack({...slack,enabled:e.target.checked})}/>Bật Slack</label>
      <label>Channel ID<input value={slack.channel} onChange={e=>setSlack({...slack,channel:e.target.value})}/></label>
      <button disabled={busy} onClick={()=>void action(async()=>{await saveSlack({...slack,channel:slack.channel||null});setNotice('Đã lưu cấu hình Slack');})}>Lưu cấu hình</button>
      <label>Nội dung<textarea value={text} onChange={e=>setText(e.target.value)}/></label>
      <button disabled={busy||!slack.enabled||!text.trim()} onClick={()=>void action(async()=>{await sendSlack(text);setText('');setNotice('Đã gửi');})}>Gửi</button>
    </section>
  </>;
}
