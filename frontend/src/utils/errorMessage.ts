// Re-export from canonical location for backward compatibility
export { formatHoursHM } from './formatters';

/**
 * Extract a readable error message from an API error response.
 * Handles Pydantic validation errors (array of {type, loc, msg, input, ctx})
 * and standard HTTPException errors (string detail).
 */
export function getErrorMessage(error: any, fallback: string = 'Ein Fehler ist aufgetreten'): string {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((err: any) => err.msg || String(err)).join(', ');
  }
  if (typeof detail === 'string') {
    return detail;
  }
  return fallback;
}
