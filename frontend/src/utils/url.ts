/**
 * Returns the URL only if it parses and uses a safe web protocol
 * (http/https). Returns null for anything else — in particular for
 * `javascript:` / `data:` / `vbscript:` URLs, which React does NOT strip
 * when placed into an `href`/`src` attribute and would otherwise execute in
 * the user's session (same class as F-049 `sanitizeGithubUrl`). Use this for
 * any URL that originates from the backend/network before rendering it as a
 * link target.
 */
export function safeHttpUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null;
    return parsed.toString();
  } catch {
    return null;
  }
}
