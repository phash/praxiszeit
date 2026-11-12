import { useEffect, useState } from 'react';

/**
 * Reagiert auf eine CSS-Media-Query. Ohne `matchMedia` (jsdom, sehr alte Browser)
 * gilt `fallback`.
 */
export function useMediaQuery(query: string, fallback = false): boolean {
  const get = () =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : fallback;
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}
