import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/fonts';
import './styles/tokens.css';
import './styles/base.css';
import './styles/print.css';
import { App } from './app/App';

const container = document.getElementById('root');
if (!container) throw new Error('#root elementi topilmadi');
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
