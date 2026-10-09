import { androidBuildConfig } from './android-build-config.mjs';

/** Only public origins belong in frontend configuration. Backend credentials stay server-side. */
function publicOrigin(name, variables) {
  const value = String(variables[name] || '').trim();
  if (!value) throw new Error(`${name} is required and must be the actual public HTTPS origin.`);
  let validated;
  try {
    validated = androidBuildConfig('production', { CAPACITOR_API_BASE_URL: value }).apiBaseUrl;
  } catch {
    throw new Error(`${name} must be a stable public HTTPS origin without credentials, a placeholder, a temporary tunnel or /api.`);
  }
  const url = new URL(validated);
  if (url.pathname !== '/') throw new Error(`${name} must be an origin without a path; the API client adds /api itself.`);
  return url.origin;
}

export function pagesBuildConfig(variables = {}) {
  const apiBaseUrl = publicOrigin('VITE_API_BASE_URL', variables);
  const studentOrigin = publicOrigin('VITE_STUDENT_APP_URL', variables);
  const adminOrigin = publicOrigin('VITE_ADMIN_APP_URL', variables);
  if (new Set([apiBaseUrl, studentOrigin, adminOrigin]).size !== 3) {
    throw new Error('API, Student Pages and Admin Pages must have three distinct origins for this deployment.');
  }
  return {
    apiBaseUrl, studentOrigin, adminOrigin,
    variables: {
      VITE_API_BASE_URL: apiBaseUrl,
      VITE_STUDENT_APP_URL: studentOrigin,
      VITE_ADMIN_APP_URL: adminOrigin,
      VITE_AUTH_COOKIE_MODE: 'false',
      VITE_NATIVE_APP: 'false',
      VITE_ANDROID_BACKEND_PLACEHOLDER: 'false',
      FIGMA_PUBLIC_URL: '',
    },
    builds: [
      { app: 'Student', arguments: ['build', '--config', 'vite.student.config.ts', '--mode', 'production'], output: 'dist/student' },
      { app: 'Admin', arguments: ['build', '--mode', 'production'], output: 'dist/admin' },
    ],
  };
}

export async function verifyPagesBackend(apiBaseUrl, fetchImpl = fetch) {
  for (const endpoint of ['health', 'ready']) {
    let response;
    let body;
    try {
      response = await fetchImpl(`${apiBaseUrl}/api/${endpoint}`, {
        method: 'GET', redirect: 'error', credentials: 'omit', cache: 'no-store',
        headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(120_000),
      });
      if (response.status !== 200) throw new Error('Unexpected status');
      body = await response.json();
    } catch {
      throw new Error(`Public HTTPS /api/${endpoint} did not return a verified 200 JSON response. No Pages build was started.`);
    }
    const passed = endpoint === 'health'
      ? body?.status === 'alive'
      : body?.status === 'ready' && body?.database === true && body?.redis === true;
    if (!passed) throw new Error(`Public HTTPS /api/${endpoint} returned an unexpected readiness body. No Pages build was started.`);
  }
  return { verifiedAt: new Date().toISOString(), health: 'alive', ready: true, database: true, redis: true };
}

export function pagesDeploymentMetadata(config, verification) {
  return {
    environment: 'staging',
    apiBaseUrl: config.apiBaseUrl, studentOrigin: config.studentOrigin, adminOrigin: config.adminOrigin,
    verification,
    backendEnvironment: {
      CORS_ORIGINS: [config.studentOrigin, config.adminOrigin, 'https://localhost'],
      STUDENT_CORS_ORIGINS: [config.studentOrigin],
      ADMIN_CORS_ORIGINS: [config.adminOrigin],
      TRUSTED_HOSTS: [new URL(config.apiBaseUrl).hostname, '127.0.0.1'],
      SESSION_COOKIE_MODE_ENABLED: 'false',
    },
    frontendAuthentication: 'Bearer',
    uploads: config.builds.map(({ app, output }) => ({ app, output })),
    note: 'Public configuration only. Upload each app output separately; keep this metadata outside both web roots. Readiness is a point-in-time check, not an availability guarantee.',
  };
}
