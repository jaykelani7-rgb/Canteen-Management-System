import http from 'node:http'
import { AuthBackend, type RegisterInput } from './auth'

const PORT = parseInt(process.env.BACKEND_PORT || '5000', 10)

function parseJsonBody(req: http.IncomingMessage): Promise<any> {
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

function sendJson(res: http.ServerResponse, statusCode: number, data: any) {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.end(JSON.stringify(data))
}

const server = http.createServer(async (req, res) => {
  const url = req.url || ''
  const [pathName] = url.split('?')

  // CORS preflight
  if (req.method === 'OPTIONS') {
    return sendJson(res, 204, {})
  }

  try {
    if (req.method === 'GET' && pathName === '/api/auth/demo-users') {
      const users = AuthBackend.getUsers()
      return sendJson(res, 200, { success: true, users })
    }

    if (req.method === 'POST' && pathName === '/api/auth/login') {
      const body = await parseJsonBody(req)
      const result = AuthBackend.login(body.rollNumber || '', body.passcode || '')
      return sendJson(res, result.success ? 200 : 401, result)
    }

    if (req.method === 'POST' && pathName === '/api/auth/register') {
      const body = (await parseJsonBody(req)) as RegisterInput
      const result = AuthBackend.register(body)
      return sendJson(res, result.success ? 201 : 400, result)
    }

    if (req.method === 'GET' && pathName === '/api/auth/me') {
      const authHeader = req.headers['authorization'] || ''
      const token = authHeader.replace(/^Bearer\s+/i, '').trim()
      const user = AuthBackend.verifyToken(token)
      if (!user) {
        return sendJson(res, 401, { success: false, message: 'Unauthorized or session expired' })
      }
      return sendJson(res, 200, { success: true, user })
    }

    if (req.method === 'POST' && pathName === '/api/auth/logout') {
      const authHeader = req.headers['authorization'] || ''
      const token = authHeader.replace(/^Bearer\s+/i, '').trim()
      AuthBackend.logout(token)
      return sendJson(res, 200, { success: true, message: 'Logged out successfully' })
    }

    if (req.method === 'POST' && pathName === '/api/auth/forgot-passcode') {
      const body = await parseJsonBody(req)
      const result = AuthBackend.requestPasscodeReset(body.rollNumber || '')
      return sendJson(res, result.success ? 200 : 404, result)
    }

    if (req.method === 'POST' && pathName === '/api/auth/reset-passcode') {
      const body = await parseJsonBody(req)
      const result = AuthBackend.resetPasscodeWithOtp(
        body.rollNumber || '',
        body.otp || '',
        body.newPasscode || ''
      )
      return sendJson(res, result.success ? 200 : 400, result)
    }

    if (pathName === '/' || pathName === '/health') {
      return sendJson(res, 200, {
        status: 'online',
        service: 'Campus Canteen OS Auth Backend',
        timestamp: new Date().toISOString(),
      })
    }

    return sendJson(res, 404, { success: false, message: `Route ${req.method} ${pathName} not found` })
  } catch (err: any) {
    console.error('[Server Error]', err)
    return sendJson(res, 500, { success: false, message: err?.message || 'Server error' })
  }
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`\n🍔 Campus Canteen OS Auth Backend is running on http://localhost:${PORT}`)
  console.log(`Endpoints available:`)
  console.log(`  - POST /api/auth/login`)
  console.log(`  - POST /api/auth/register`)
  console.log(`  - GET  /api/auth/me`)
  console.log(`  - POST /api/auth/logout`)
  console.log(`  - POST /api/auth/forgot-passcode`)
  console.log(`  - POST /api/auth/reset-passcode`)
  console.log(`  - GET  /api/auth/demo-users\n`)
})
