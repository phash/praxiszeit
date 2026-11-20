import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AxiosError } from 'axios';
import apiClient from './client';
import { useReportStore } from '../stores/reportStore';

const originalAdapter = apiClient.defaults.adapter;

function failWith(status: number) {
  apiClient.defaults.adapter = (config) => {
    const response = { data: {}, status, statusText: '', headers: {}, config, request: {} };
    return Promise.reject(new AxiosError('fail', String(status), config, {}, response as never));
  };
}

beforeEach(() => useReportStore.setState({ lastServerError: null, request: null }));
afterEach(() => { apiClient.defaults.adapter = originalAdapter; });

describe('5xx-Merker im Antwort-Interceptor (#557)', () => {
  it('records 5xx with path without query', async () => {
    failWith(500);
    await expect(apiClient.post('/time-entries/clock-out?x=1', {})).rejects.toBeTruthy();
    const last = useReportStore.getState().lastServerError;
    expect(last).toMatchObject({ status: 500, method: 'POST', path: '/api/time-entries/clock-out' });
    expect(typeof last?.at).toBe('number');
  });

  it('does not record feedback endpoints', async () => {
    failWith(502);
    await expect(apiClient.post('/feedback/send', {})).rejects.toBeTruthy();
    expect(useReportStore.getState().lastServerError).toBeNull();
  });

  it('merkt sich 4xx und Methoden außerhalb der Liste nicht', async () => {
    failWith(422);
    await expect(apiClient.get('/admin/users')).rejects.toBeTruthy();
    expect(useReportStore.getState().lastServerError).toBeNull();
    failWith(503);
    await expect(apiClient.head('/health')).rejects.toBeTruthy();
    expect(useReportStore.getState().lastServerError).toBeNull();
  });

  it('normalisiert eine absolute URL auf den Pfad', async () => {
    failWith(500);
    await expect(apiClient.get('http://localhost/api/admin/errors/?a=b')).rejects.toBeTruthy();
    expect(useReportStore.getState().lastServerError?.path).toBe('/api/admin/errors/');
  });
});
