import React from 'react'
import ReactDOM from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './index.css'

// F-058: Prompt-based PWA update flow.
//
// On deploy, the service worker downloads the new assets in the background
// and then enters the "waiting" state. Instead of auto-reloading (which
// destroys mid-form user input), we show a confirmation dialog so the
// user can finish what they're doing first.
//
// Fallback: if the user dismisses the dialog, the update is applied on
// the next full page navigation anyway.
const updateSW = registerSW({
  onNeedRefresh() {
    // Use window.confirm as the minimal dependency-free prompt. Upgrade
    // to a toast-based flow once ToastContext exposes an imperative API
    // outside of React (see TODO below).
    // TODO: expose a useToast-style imperative handle for this.
    if (window.confirm('Eine neue Version ist verfügbar. Jetzt aktualisieren?')) {
      void updateSW(true);
    }
  },
  onOfflineReady() {
    // Optional: could show a "ready for offline use" hint.
  },
  // Issue #84: Bei self-signed Cert (typisch in Native-LAN-Deployments) verweigert
  // Chrome die SW-Registrierung mit SecurityError. Ohne Handler ist das eine
  // unhandled rejection + roter Console-Eintrag bei jedem Page-Load. Wir
  // schlucken sie bewusst — die App funktioniert auch ohne SW, nur PWA-Features
  // (Offline, Installierbarkeit, Background-Update-Download) sind aus.
  onRegisterError(error) {
    const msg = String(error?.message ?? error);
    if (msg.includes('SSL') || msg.includes('SecurityError') || msg.includes('certificate')) {
      console.info(
        '[PWA] ServiceWorker-Registrierung ausgesetzt — vermutlich self-signed Cert. ' +
        'App funktioniert normal weiter; PWA-Features (Offline, Installation) bleiben aus. ' +
        'Um sie zu aktivieren: Cert system-weit als Trusted Root importieren.'
      );
    } else {
      console.warn('[PWA] ServiceWorker-Registrierung fehlgeschlagen:', error);
    }
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
