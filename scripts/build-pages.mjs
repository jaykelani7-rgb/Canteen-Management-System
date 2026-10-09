import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pagesBuildConfig, verifyPagesBackend, pagesDeploymentMetadata } from './pages-build-config.mjs';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
try {
  if (process.argv.length !== 2) throw new Error('Usage: node scripts/build-pages.mjs (set the three public VITE_* origins in the process environment first).');
  const config = pagesBuildConfig(process.env);
  console.log('Checking public backend health and database/Redis readiness before building Pages assets.');
  const verification = await verifyPagesBackend(config.apiBaseUrl);
  const metadataPath = path.join(repo, 'dist', 'pages-deployment.json');
  // A failed later build must not leave an old manifest certifying mixed output directories.
  fs.rmSync(metadataPath, { force: true });
  const vite = path.join(repo, 'node_modules', 'vite', 'bin', 'vite.js');
  for (const build of config.builds) {
    console.log(`Building ${build.app} web into ${build.output}.`);
    const result = spawnSync(process.execPath, [vite, ...build.arguments], {
      cwd: repo, stdio: 'inherit', env: { ...process.env, ...config.variables },
    });
    if (result.error || result.status !== 0) throw new Error(`${build.app} web build failed. No deployment manifest was produced.`);
    const output = path.join(repo, build.output);
    if (!fs.existsSync(path.join(output, 'index.html'))) throw new Error(`${build.app} build did not produce its index.html.`);
    const javascript = fs.readdirSync(path.join(output, 'assets'))
      .filter(file => file.endsWith('.js'))
      .map(file => fs.readFileSync(path.join(output, 'assets', file), 'utf8'));
    if (!javascript.some(content => content.includes(config.apiBaseUrl))) throw new Error(`${build.app} bundle does not contain the configured API origin.`);
    if (build.app === 'Admin' && !javascript.some(content => content.includes(config.studentOrigin))) throw new Error('Admin bundle does not contain the configured Student web origin.');
  }
  fs.writeFileSync(metadataPath, JSON.stringify(pagesDeploymentMetadata(config, verification), null, 2) + '\n');
  console.log('PASS both web bundles use the verified backend and Bearer authentication.');
  console.log('Public CORS/hosting metadata: dist/pages-deployment.json (do not upload this file).');
  console.log('Upload only dist/student and dist/admin to their respective Cloudflare Pages projects. No upload or Android rebuild was performed.');
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Pages build preparation failed.');
  process.exitCode = 1;
}
