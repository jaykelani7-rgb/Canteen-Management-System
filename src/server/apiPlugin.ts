import type { Plugin, Connect } from 'vite'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { AuthBackend, type RegisterInput } from './auth'

function parseJsonBody(req: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let body = ''
    req.on('data', (chunk) => {
      body += chunk
    })
    req.on('end', () => {
      if (!body) return resolve({})
      try {
        resolve(JSON.parse(body))
      } catch (err) {
        reject(new Error('Invalid JSON body'))
      }
    })
    req.on('error', reject)
  })
}

function sendJson(res: ServerResponse, statusCode: number, data: any) {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.end(JSON.stringify(data))
}

export function authApiPlugin(): Plugin {
  return {
    name: 'campus-canteen-auth-api',
    configureServer(server) {
      server.middlewares.use(async (req: Connect.IncomingMessage, res: ServerResponse, next: Connect.NextFunction) => {
        const url = req.url || ''
        const [pathName] = url.split('?')

        // Handle CORS preflight
        if (req.method === 'OPTIONS' && pathName.startsWith('/api/')) {
          sendJson(res, 204, {})
          return
        }

        if (!pathName.startsWith('/api/auth')) {
          return next()
        }

        try {
          // 1. GET /api/auth/demo-users
          if (req.method === 'GET' && pathName === '/api/auth/demo-users') {
            const users = AuthBackend.getUsers()
            return sendJson(res, 200, { success: true, users })
          }

          // 2. POST /api/auth/login
          if (req.method === 'POST' && pathName === '/api/auth/login') {
            const body = await parseJsonBody(req)
            const { rollNumber, passcode } = body
            const result = AuthBackend.login(rollNumber || '', passcode || '')
            return sendJson(res, result.success ? 200 : 401, result)
          }

          // 3. POST /api/auth/register
          if (req.method === 'POST' && pathName === '/api/auth/register') {
            const body = (await parseJsonBody(req)) as RegisterInput
            const result = AuthBackend.register(body)
            return sendJson(res, result.success ? 201 : 400, result)
          }

          // 4. GET /api/auth/me
          if (req.method === 'GET' && pathName === '/api/auth/me') {
            const authHeader = req.headers['authorization'] || ''
            const token = authHeader.replace(/^Bearer\s+/i, '').trim()
            const user = AuthBackend.verifyToken(token)

            if (!user) {
              return sendJson(res, 401, {
                success: false,
                message: 'Unauthorized or session expired',
              })
            }
            return sendJson(res, 200, { success: true, user })
          }

          // 5. POST /api/auth/logout
          if (req.method === 'POST' && pathName === '/api/auth/logout') {
            const authHeader = req.headers['authorization'] || ''
            const token = authHeader.replace(/^Bearer\s+/i, '').trim()
            AuthBackend.logout(token)
            return sendJson(res, 200, {
              success: true,
              message: 'Logged out successfully',
            })
          }

          // 6. POST /api/auth/forgot-passcode
          if (req.method === 'POST' && pathName === '/api/auth/forgot-passcode') {
            const body = await parseJsonBody(req)
            const { rollNumber } = body
            const result = AuthBackend.requestPasscodeReset(rollNumber || '')
            return sendJson(res, result.success ? 200 : 404, result)
          }

          // 7. POST /api/auth/reset-passcode
          if (req.method === 'POST' && pathName === '/api/auth/reset-passcode') {
            const body = await parseJsonBody(req)
            const { rollNumber, otp, newPasscode } = body
            const result = AuthBackend.resetPasscodeWithOtp(
              rollNumber || '',
              otp || '',
              newPasscode || ''
            )
            return sendJson(res, result.success ? 200 : 400, result)
          }

          return sendJson(res, 404, {
            success: false,
            message: `Route ${req.method} ${pathName} not found`,
          })
        } catch (error: any) {
          console.error('[Auth API Error]', error)
          return sendJson(res, 500, {
            success: false,
            message: error?.message || 'Internal Server Error',
          })
        }
      })
    },
  }
}
