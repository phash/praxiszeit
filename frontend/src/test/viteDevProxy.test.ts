// @vitest-environment node
import { describe, it, expect } from 'vitest';
import config from '../../vite.config';

// Gesamtreview 1.20 B6: Bare-Collection-Routen (`GET /api/dashboard`,
// `/api/absences`, `/api/time-entries?…`) antworten mit einem 307 auf den
// Pfad mit Schrägstrich; FastAPI baut die ABSOLUTE Location aus dem
// Host-Header. Mit `changeOrigin: true` setzte der Vite-Dev-Proxy diesen auf
// das Backend (`localhost:8000`) — der Browser folgte im `npm run dev` direkt
// dorthin, also cross-origin (CORS-/Cookie-Fehler statt Daten). Dasselbe
// Problem löst nginx in Docker mit `Host $http_host` (#dashboard-307, 1.8.6).
// Nur die Entwicklungsumgebung ist betroffen: Produktion läuft über nginx bzw.
// nativ direkt über uvicorn, der Vite-Dev-Server ist dort nicht beteiligt.
describe('Vite-Dev-Proxy /api', () => {
  it('reicht den Host-Header des Browsers durch (changeOrigin: false)', () => {
    const resolved = typeof config === 'function' ? null : config;
    const proxy = resolved?.server?.proxy?.['/api'];
    expect(proxy).toMatchObject({ target: 'http://localhost:8000', changeOrigin: false });
  });
});
