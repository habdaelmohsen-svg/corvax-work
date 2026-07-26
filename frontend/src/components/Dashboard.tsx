import {HashRouter} from 'react-router-dom';
import {Shell} from '../dashboard/Shell';
import type {Lang} from '../dashboard/types';
import '../styles/dashboard.css';

export function Dashboard({lang, setLang, onChangeCompany, onLogout}: {
  lang: Lang;
  setLang: (lang: Lang) => void;
  onChangeCompany: () => void;
  onLogout: () => void;
}) {
  return <HashRouter><Shell lang={lang} setLang={setLang} onChangeCompany={onChangeCompany} onLogout={onLogout}/></HashRouter>;
}
