export default function SettingsLink() {
  return <a className="settings-link" href="/?page=settings&tab=kaggle-proxy" aria-label="Cài đặt" title="Cài đặt">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="m9 3-.6 2.1-1.6.9-2.1-.5-2 3.5 1.5 1.6v1.8l-1.5 1.6 2 3.5 2.1-.5 1.6.9.6 2.1h4l.6-2.1 1.6-.9 2.1.5 2-3.5-1.5-1.6v-1.8l1.5-1.6-2-3.5-2.1.5-1.6-.9L13 3Z"/>
      <circle cx="11" cy="11.5" r="3"/>
    </svg>
  </a>;
}
