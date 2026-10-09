import { isIP } from 'node:net';

/** Public build configuration only. Never put private credentials in VITE_* variables. */
export const STAGING_API_PLACEHOLDER = 'https://staging-api.canteenos.example';
export const ANDROID_ENVIRONMENTS = ['development', 'staging', 'production'];

function ipv4IsPublic(host) {
  const [a, b, c] = host.split('.').map(Number);
  return !(a === 0 || a === 10 || a === 127 || a >= 224 ||
    (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && (b === 168 || (b === 0 && (c === 0 || c === 2)) || (b === 88 && c === 99))) ||
    (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) ||
    (a === 203 && b === 0 && c === 113));
}

function ipv6IsPublic(host) {
  // URL canonicalizes embedded IPv4 into hexadecimal; isIP has validated syntax.
  const [left, right] = host.split('::');
  const start = left ? left.split(':') : [];
  const end = right ? right.split(':') : [];
  const words = right === undefined ? start : [...start, ...Array(8 - start.length - end.length).fill('0'), ...end];
  const address = words.reduce((value, word) => (value << 16n) | BigInt('0x' + word), 0n);
  const prefix = (network, bits) => address >> BigInt(128 - bits) === network >> BigInt(128 - bits);
  // Only globally routed unicast 2000::/3; exclude documentation and special-purpose ranges.
  if (!prefix(0x20000000000000000000000000000000n, 3)) return false;
  return !prefix(0x20010000000000000000000000000000n, 23) &&
    !prefix(0x20010db8000000000000000000000000n, 32) &&
    !prefix(0x20020000000000000000000000000000n, 16) &&
    !prefix(0x3fff0000000000000000000000000000n, 20);
}

const placeholderDomains = ['example', 'example.com', 'example.org', 'example.net', 'invalid', 'test'];
const privateDomains = ['localhost', 'local', 'internal', 'home.arpa', 'lan', 'corp', 'private', 'intranet', 'onion'];
const temporaryDomains = ['trycloudflare.com', 'ngrok.io', 'ngrok.app', 'ngrok-free.app', 'ngrok-free.dev', 'loca.lt', 'localtunnel.me', 'localhost.run', 'lhr.life', 'serveo.net', 'tunnelmole.net', 'pinggy.link', 'pinggy.io', 'zrok.io'];
const matchesDomain = (host, domain) => host === domain || host.endsWith('.' + domain);

export function androidBuildConfig(environment = 'staging', variables = {}) {
  if (!ANDROID_ENVIRONMENTS.includes(environment)) throw new Error('Android environment must be development, staging or production.');
  const configured = String(variables.CAPACITOR_API_BASE_URL || '').trim();
  if (environment === 'production' && !configured) throw new Error('Production requires CAPACITOR_API_BASE_URL pointing to a deployed HTTPS backend.');
  let url;
  try { url = new URL(configured || STAGING_API_PLACEHOLDER); } catch { throw new Error('CAPACITOR_API_BASE_URL must be an absolute HTTPS URL.'); }
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '').replace(/\.+$/, '');
  const ipVersion = isIP(host);
  const privateHost = privateDomains.some(domain => matchesDomain(host, domain)) ||
    (ipVersion === 4 && !ipv4IsPublic(host)) || (ipVersion === 6 && !ipv6IsPublic(host)) ||
    (!ipVersion && !host.includes('.'));
  let pathname;
  try { pathname = decodeURIComponent(url.pathname); } catch { throw new Error('CAPACITOR_API_BASE_URL contains an invalid path.'); }
  if (/\/api\/?$/i.test(pathname)) throw new Error('CAPACITOR_API_BASE_URL must not end in /api; the client adds /api itself.');
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || privateHost || temporaryDomains.some(domain => matchesDomain(host, domain))) {
    throw new Error('Use a stable public HTTPS backend URL without credentials, query, fragment, private/reserved addresses or a temporary tunnel.');
  }
  const placeholder = placeholderDomains.some(domain => matchesDomain(host, domain));
  if (environment === 'production' && placeholder) throw new Error('Production cannot use a documentation placeholder; deploy and verify the HTTPS backend first.');
  // Normalize a trailing DNS root dot so equivalent origins do not differ in CORS/build assertions.
  url.hostname = ipVersion === 6 ? '[' + host + ']' : host;
  return { environment, apiBaseUrl: url.href.replace(/\/+$/, ''), placeholder, mode: `android-${environment}`, outDir: 'dist/student-android' };
}
