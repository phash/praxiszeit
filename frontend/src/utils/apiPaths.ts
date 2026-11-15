/**
 * Log-Audit 2026-11-15 (Punkt 17, NET-3): Basis-Routen, die das Backend als
 * `@router.get("/")` bzw. `@router.post("/")` registriert. Ohne Schrägstrich
 * antwortet FastAPI mit 307 und der Browser fragt ein zweites Mal (1149
 * Umleitungen in 15 Tagen an einem Kundenserver). Der Request-Interceptor in
 * `api/client.ts` hängt den Schrägstrich an, damit keine Aufrufstelle ihn
 * vergessen kann.
 *
 * NUR Routen mit "/" eintragen: Routen mit "" (z. B. `/admin/backups`,
 * `/reduced-days`) würden mit Schrägstrich ihrerseits umleiten. Quelle:
 * `grep -rn '@router.\(get\|post\)("/"' backend/app/routers` (Präfix + "/").
 */
export const COLLECTION_ROUTES: ReadonlySet<string> = new Set([
  '/absences',
  '/dashboard',
  '/admin/reduced-days',
  '/admin/errors',
  '/vacation-requests',
  '/holidays',
  '/change-requests',
  '/time-entries',
  '/company-closures',
]);

/** Hängt an eine Basis-Route den Schrägstrich an (Abfrage bleibt erhalten). */
export function withCollectionSlash<T extends string | undefined>(url: T): T {
  if (!url) return url;
  const q = url.indexOf('?');
  const path = q === -1 ? url : url.slice(0, q);
  if (!COLLECTION_ROUTES.has(path)) return url;
  return (`${path}/` + (q === -1 ? '' : url.slice(q))) as T;
}
