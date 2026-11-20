import { beforeEach, describe, expect, it } from 'vitest';
import { useReportStore } from './reportStore';

const hint = { status: 500, method: 'POST', path: '/api/time-entries/' };

beforeEach(() => {
  useReportStore.setState({ lastServerError: null, request: null });
});

describe('reportStore', () => {
  it('takeRecentServerError returns hint within window once', () => {
    useReportStore.getState().recordServerError(hint, 1000);
    expect(useReportStore.getState().takeRecentServerError(4000)).toEqual(hint);
    expect(useReportStore.getState().takeRecentServerError(4000)).toBeNull();
  });

  it('ignores hints older than window', () => {
    useReportStore.getState().recordServerError(hint, 1000);
    expect(useReportStore.getState().takeRecentServerError(6001)).toBeNull();
    // auch ein veralteter Hinweis wird verworfen
    expect(useReportStore.getState().lastServerError).toBeNull();
  });

  it('openReport/closeReport setzen und leeren die Anfrage', () => {
    useReportStore.getState().openReport({ serverError: hint, initialTitle: 't' });
    expect(useReportStore.getState().request).toEqual({ serverError: hint, initialTitle: 't' });
    useReportStore.getState().closeReport();
    expect(useReportStore.getState().request).toBeNull();
  });
});
