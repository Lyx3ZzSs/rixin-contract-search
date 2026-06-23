import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles/contract-agent.css';

const app = document.querySelector('#app');

if (!app) {
  throw new Error('Missing #app root element');
}

createRoot(app).render(
  <StrictMode>
    <App />
  </StrictMode>
);
