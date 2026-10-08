import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'
import path from 'node:path'

function studentServiceWorker(): Plugin {
  return {
    name: 'student-static-service-worker',
    apply: 'build',
    generateBundle(_options, bundle) {
      const assets = ['/', '/index.html', '/offline.html', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', ...Object.keys(bundle).filter(name => name.startsWith('assets/')).map(name => '/' + name)]
      const template = readFileSync(path.resolve(__dirname, 'student/public/sw.js'), 'utf8')
      this.emitFile({ type: 'asset', fileName: 'sw.js', source: template.replace('/* PRECACHE_ASSETS */ []', JSON.stringify(assets)).replace('student-static-v1', 'student-static-' + Date.now()) })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const proxy = { '/api': { target: env.FASTAPI_URL || 'http://127.0.0.1:8000', changeOrigin: true } }
  const https = env.HTTPS_KEY_FILE && env.HTTPS_CERT_FILE ? { key: readFileSync(env.HTTPS_KEY_FILE), cert: readFileSync(env.HTTPS_CERT_FILE) } : undefined
  return {
    root: path.resolve(__dirname, 'student'),
    envDir: __dirname,
    plugins: [react(), tailwindcss(), studentServiceWorker()],
    resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
    build: { outDir: path.resolve(__dirname, 'dist/student'), emptyOutDir: true },
    server: { host: '0.0.0.0', port: 5173, strictPort: true, proxy, https, fs: { allow: [__dirname] }, watch: { ignored: ['**/backend/**', '**/dist/**', '**/.figma/**'] } },
    preview: { host: '0.0.0.0', port: 5173, strictPort: true, proxy, https },
  }
})
