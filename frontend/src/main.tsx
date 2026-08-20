import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/theme.css';
import './styles/rc27_4_hardening.css';
import './styles/rc27_4_design_h4_1.css';
import './styles/rc27_4_ai_assistant_h5.css';
import './styles/financialReports.css';
import './styles/corvax_mui_v16.css';

// A deployment can replace hashed Vite chunks while an older page is still open.
// Recover once from that stale-chunk state instead of leaving the dashboard blank.
window.addEventListener('vite:preloadError',((event:Event)=>{
  event.preventDefault();
  const key='corvax-vite-preload-reload-at';
  const lastReload=Number(window.sessionStorage.getItem(key)||0);
  if(Date.now()-lastReload>60000){
    window.sessionStorage.setItem(key,String(Date.now()));
    window.location.reload();
  }
}) as EventListener);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
