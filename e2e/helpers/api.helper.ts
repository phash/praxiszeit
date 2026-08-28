// Default: the frontend nginx /api proxy on :80. Overridable via E2E_API_BASE so
// the suite can run against an alternate host port when :80 is taken.
//
// #461 W-2: faellt E2E_API_BASE weg, wird es aus E2E_BASE_URL abgeleitet. Vorher
// nutzten die Seiten E2E_BASE_URL und dieser Helfer E2E_API_BASE — wer nur
// E2E_BASE_URL=https://remote setzte, liess die Tests gegen den entfernten Host
// laufen, waehrend jeder API-Aufruf (inkl. der mandantenweiten Umschaltung von
// `shift_planning_enabled`) auf der LOKALEN Instanz landete.
const API_BASE =
  process.env.E2E_API_BASE ??
  (process.env.E2E_BASE_URL
    ? `${process.env.E2E_BASE_URL.replace(/\/+$/, '')}/api`
    : 'http://localhost/api');

// #461 W-2: ohne Zeitgrenze haengt ein Host, der die TCP-Verbindung annimmt aber
// nie antwortet, den gesamten Lauf im "global setup" fest — `fetch` hat von sich
// aus KEINEN Timeout.
const REQUEST_TIMEOUT_MS = 30_000;
const signal = () => AbortSignal.timeout(REQUEST_TIMEOUT_MS);

interface LoginResponse {
  access_token: string;
  user: {
    id: string;
    username: string;
    role: string;
    first_name: string;
    last_name: string;
    email: string | null;
    weekly_hours: number;
    work_days_per_week: number;
    vacation_days: number;
    calendar_color: string | null;
    is_active: boolean;
    totp_enabled: boolean;
    created_at: string;
    use_daily_schedule: boolean;
  };
}

export class ApiHelper {
  token: string = '';
  userData: LoginResponse['user'] | null = null;
  /**
   * F-023: Raw refresh_token cookie value captured from the login
   * response. Tests inject this into the Playwright BrowserContext via
   * context.addCookies() so the frontend's authStore.hydrate() can
   * restore the in-memory access token on first mount — without doing
   * a second login call (which would trip the 5/minute rate limit).
   */
  refreshCookie: string = '';

  async login(username: string, password: string): Promise<LoginResponse> {
    const maxRetries = 5;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        signal: signal(),
      });
      if (res.status === 429 && attempt < maxRetries - 1) {
        // Rate limited (5/min on login) - wait and retry
        const delay = 12_000 * (attempt + 1);
        await new Promise((r) => setTimeout(r, delay));
        continue;
      }
      if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`);

      // Extract the HttpOnly refresh_token cookie so tests can seed it
      // into the Playwright BrowserContext. `fetch` exposes the header
      // via getSetCookie() in recent Node versions; fall back to `get`
      // for older engines where it's merged into a single string.
      const setCookieHeader =
        typeof (res.headers as any).getSetCookie === 'function'
          ? (res.headers as any).getSetCookie().join('; ')
          : res.headers.get('set-cookie') ?? '';
      const match = setCookieHeader.match(/refresh_token=([^;]+)/);
      if (match) this.refreshCookie = match[1];

      const data = await res.json();
      this.token = data.access_token;
      this.userData = data.user;
      return data;
    }
    throw new Error('Login failed: max retries exceeded');
  }

  setToken(token: string) {
    this.token = token;
  }

  private headers(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
    };
  }

  async get(path: string): Promise<any> {
    const res = await fetch(`${API_BASE}${path}`, { headers: this.headers(), signal: signal() });
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  async post(path: string, body?: any): Promise<any> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: this.headers(),
      body: body ? JSON.stringify(body) : undefined,
      signal: signal(),
    });
    if (!res.ok) throw new Error(`POST ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  async put(path: string, body: any): Promise<any> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: this.headers(),
      body: JSON.stringify(body),
      signal: signal(),
    });
    // #461 K-8: den Antwortrumpf mitnehmen. PUT ist der meistgenutzte Aufruf der
    // Suite; ohne ihn verbirgt ein 400 sein `detail` und der Fehlschlag lautet
    // nur "PUT /... failed: 400".
    if (!res.ok) throw new Error(`PUT ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  async delete(path: string): Promise<void> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: this.headers(),
      signal: signal(),
    });
    if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status} ${await res.text()}`);
  }

  async getRaw(path: string): Promise<Response> {
    return fetch(`${API_BASE}${path}`, { headers: this.headers(), signal: signal() });
  }
}
