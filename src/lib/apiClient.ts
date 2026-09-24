import { AuthBackend, type UserProfile, type AuthResponse, type RegisterInput, INITIAL_USERS } from '../server/auth'

const TOKEN_KEY = 'sco_auth_token'
const USER_KEY = 'sco_auth_user'

export const apiClient = {
  getToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },

  setToken(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token)
      else localStorage.removeItem(TOKEN_KEY)
    } catch (e) {
      console.error(e)
    }
  },

  getCachedUser(): UserProfile | null {
    try {
      const data = localStorage.getItem(USER_KEY)
      return data ? JSON.parse(data) : null
    } catch {
      return null
    }
  },

  setCachedUser(user: UserProfile | null) {
    try {
      if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
      else localStorage.removeItem(USER_KEY)
    } catch (e) {
      console.error(e)
    }
  },

  async login(rollNumber: string, passcode: string): Promise<AuthResponse> {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rollNumber, passcode }),
      })
      const data = await res.json()
      if (data.token) {
        this.setToken(data.token)
        this.setCachedUser(data.user)
      }
      return data
    } catch (err) {
      console.warn('[apiClient] Fetch failed, falling back to local AuthBackend:', err)
      const res = AuthBackend.login(rollNumber, passcode)
      if (res.token && res.user) {
        this.setToken(res.token)
        this.setCachedUser(res.user)
      }
      return res
    }
  },

  async register(input: RegisterInput): Promise<AuthResponse> {
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      })
      const data = await res.json()
      if (data.token && data.user) {
        this.setToken(data.token)
        this.setCachedUser(data.user)
      }
      return data
    } catch (err) {
      console.warn('[apiClient] Register fetch failed, falling back to local AuthBackend:', err)
      const res = AuthBackend.register(input)
      if (res.token && res.user) {
        this.setToken(res.token)
        this.setCachedUser(res.user)
      }
      return res
    }
  },

  async getMe(): Promise<{ success: boolean; user?: UserProfile }> {
    const token = this.getToken()
    if (!token) {
      const cached = this.getCachedUser()
      if (cached) return { success: true, user: cached }
      // Default to initial demo user if nothing stored
      return { success: true, user: INITIAL_USERS[0] }
    }

    try {
      const res = await fetch('/api/auth/me', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        const data = await res.json()
        if (data.user) {
          this.setCachedUser(data.user)
          return { success: true, user: data.user }
        }
      }
    } catch (err) {
      console.warn('[apiClient] getMe fetch failed, checking local token:', err)
    }

    // Fallback to local auth or cached user
    const localUser = AuthBackend.verifyToken(token) || this.getCachedUser() || INITIAL_USERS[0]
    return { success: true, user: localUser }
  },

  async logout(): Promise<boolean> {
    const token = this.getToken()
    this.setToken(null)
    this.setCachedUser(null)

    if (token) {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
        })
      } catch (err) {
        console.warn('[apiClient] Logout error:', err)
        AuthBackend.logout(token)
      }
    }
    return true
  },

  async requestPasscodeReset(rollNumber: string): Promise<{ success: boolean; message: string; otp?: string }> {
    try {
      const res = await fetch('/api/auth/forgot-passcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rollNumber }),
      })
      return await res.json()
    } catch (err) {
      console.warn('[apiClient] forgot-passcode fetch failed, falling back to local AuthBackend:', err)
      return AuthBackend.requestPasscodeReset(rollNumber)
    }
  },

  async resetPasscode(rollNumber: string, otp: string, newPasscode: string): Promise<AuthResponse> {
    try {
      const res = await fetch('/api/auth/reset-passcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rollNumber, otp, newPasscode }),
      })
      const data = await res.json()
      if (data.token && data.user) {
        this.setToken(data.token)
        this.setCachedUser(data.user)
      }
      return data
    } catch (err) {
      console.warn('[apiClient] resetPasscode fetch failed, falling back to local AuthBackend:', err)
      const res = AuthBackend.resetPasscodeWithOtp(rollNumber, otp, newPasscode)
      if (res.token && res.user) {
        this.setToken(res.token)
        this.setCachedUser(res.user)
      }
      return res
    }
  },

  async getDemoUsers(): Promise<UserProfile[]> {
    try {
      const res = await fetch('/api/auth/demo-users')
      const data = await res.json()
      if (data.users && Array.isArray(data.users)) {
        return data.users
      }
    } catch {
      // Fallback
    }
    return AuthBackend.getUsers()
  },
}
