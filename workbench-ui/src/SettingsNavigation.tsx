export type SettingsTab='kaggle-proxy'|'config-agent'|'slack'|'remote';

const tabs: {id:SettingsTab;label:string}[]=[
  {id:'kaggle-proxy',label:'Kaggle proxy'},
  {id:'config-agent',label:'Config agent'},
  {id:'slack',label:'Slack'},
  {id:'remote',label:'Remote'},
];

export default function SettingsNavigation({active}: {active:SettingsTab}){
  return <nav className="settings-nav" aria-label="Settings">{tabs.map(tab=><a key={tab.id} className={active===tab.id?'active':undefined} href={'/?page=settings&tab='+tab.id} aria-current={active===tab.id?'page':undefined}>{tab.label}</a>)}</nav>;
}
