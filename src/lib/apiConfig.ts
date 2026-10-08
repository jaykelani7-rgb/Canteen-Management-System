/** Both apps use the existing FastAPI service through /api or an explicit deployment origin. */
export function apiUrl(path: string): string {
  const configured = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
  return `${configured}${path.startsWith('/') ? path : '/' + path}`;
}
