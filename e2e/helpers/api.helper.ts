const API_BASE = 'http://localhost/api';

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
  private token: string = '';

  async login(username: string, password: string): Promise<LoginResponse> {
    const maxRetries = 5;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (res.status === 429 && attempt < maxRetries - 1) {
        // Rate limited (5/min on login) - wait and retry
        const delay = 12_000 * (attempt + 1);
        await new Promise((r) => setTimeout(r, delay));
        continue;
      }
      if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`);
      const data = await res.json();
      this.token = data.access_token;
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
    const res = await fetch(`${API_BASE}${path}`, { headers: this.headers() });
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return res.json();
  }

  async post(path: string, body?: any): Promise<any> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: this.headers(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`POST ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  async put(path: string, body: any): Promise<any> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: this.headers(),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PUT ${path} failed: ${res.status}`);
    return res.json();
  }

  async delete(path: string): Promise<void> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: this.headers(),
    });
    if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`);
  }

  async getRaw(path: string): Promise<Response> {
    return fetch(`${API_BASE}${path}`, { headers: this.headers() });
  }
}
