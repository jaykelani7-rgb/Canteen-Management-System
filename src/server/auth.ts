export interface UserProfile {
  id: string
  rollNumber: string // e.g. "21CS1042"
  name: string
  branch: string // e.g. "B.Tech CSE"
  email: string
  phone: string
  walletBalance: number
  upiId: string
  totalOrders: number
  totalSpent: number
  savedMinutes: number
  createdAt: string
}

export interface UserAccount extends UserProfile {
  passcode: string // In production, stored as hashed
  sessionTokens: string[]
}

// In-memory student user database pre-seeded with sample students
export const INITIAL_USERS: UserAccount[] = [
  {
    id: 'usr_aarav',
    rollNumber: '21CS1042',
    name: 'Aarav Sharma',
    branch: 'B.Tech Computer Science & Eng.',
    email: 'aarav.sharma@campus.edu',
    phone: '+91 98765 43210',
    walletBalance: 340,
    upiId: 'aarav@campuspay',
    totalOrders: 38,
    totalSpent: 4200,
    savedMinutes: 12,
    passcode: '000000', // Supports 000000 and 123456
    sessionTokens: [],
    createdAt: new Date('2024-08-01').toISOString(),
  },
  {
    id: 'usr_priya',
    rollNumber: '21IT2015',
    name: 'Priya Patel',
    branch: 'B.Tech Information Technology',
    email: 'priya.patel@campus.edu',
    phone: '+91 98765 11223',
    walletBalance: 520,
    upiId: 'priya@campuspay',
    totalOrders: 42,
    totalSpent: 5120,
    savedMinutes: 18,
    passcode: '000000',
    sessionTokens: [],
    createdAt: new Date('2024-08-05').toISOString(),
  },
  {
    id: 'usr_rohan',
    rollNumber: '22EC3088',
    name: 'Rohan Verma',
    branch: 'B.Tech Electronics & Comm.',
    email: 'rohan.verma@campus.edu',
    phone: '+91 98765 99887',
    walletBalance: 150,
    upiId: 'rohan@campuspay',
    totalOrders: 19,
    totalSpent: 1850,
    savedMinutes: 6,
    passcode: '000000',
    sessionTokens: [],
    createdAt: new Date('2024-09-10').toISOString(),
  },
  {
    id: 'usr_ananya',
    rollNumber: '23ME5001',
    name: 'Ananya Iyer',
    branch: 'B.Tech Mechanical Engineering',
    email: 'ananya.iyer@campus.edu',
    phone: '+91 98765 66554',
    walletBalance: 780,
    upiId: 'ananya@campuspay',
    totalOrders: 12,
    totalSpent: 1400,
    savedMinutes: 4,
    passcode: '000000',
    sessionTokens: [],
    createdAt: new Date('2024-10-01').toISOString(),
  },
]

// Global in-memory store (maintained per server runtime or local storage in client)
let usersDatabase: UserAccount[] = [...INITIAL_USERS]
const activeSessions = new Map<string, string>() // token -> userId
const passwordResetOtps = new Map<string, { otp: string; expiresAt: number }>() // rollNumber -> otp

function stripSensitive(user: UserAccount): UserProfile {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { passcode, sessionTokens, ...profile } = user
  return profile
}

function generateToken(userId: string): string {
  const rand = Math.random().toString(36).substring(2) + Date.now().toString(36)
  return `sco_jwt_${userId}_${rand}`
}

export function normalizeRollNumber(roll: string): string {
  return roll.trim().toUpperCase().replace(/\s+/g, '')
}

export interface AuthResponse {
  success: boolean
  message: string
  user?: UserProfile
  token?: string
}

export interface RegisterInput {
  rollNumber: string
  name: string
  branch?: string
  phone?: string
  email?: string
  passcode: string
}

export const AuthBackend = {
  getUsers(): UserProfile[] {
    return usersDatabase.map(stripSensitive)
  },

  login(rollNumber: string, passcode: string): AuthResponse {
    const normRoll = normalizeRollNumber(rollNumber)
    if (!normRoll || !passcode) {
      return { success: false, message: 'Please provide roll number and passcode.' }
    }

    const user = usersDatabase.find(
      (u) => normalizeRollNumber(u.rollNumber) === normRoll
    )

    if (!user) {
      return {
        success: false,
        message: `Student account for roll "${normRoll}" was not found. Please register or check roll number.`,
      }
    }

    // Support both the account's passcode and standard demo passcode '123456' or '000000'
    const isMatch = user.passcode === passcode || passcode === '123456' || passcode === '000000'
    if (!isMatch) {
      return {
        success: false,
        message: 'Incorrect passcode. Try default "000000" or reset your passcode.',
      }
    }

    const token = generateToken(user.id)
    activeSessions.set(token, user.id)
    user.sessionTokens.push(token)

    return {
      success: true,
      message: `Welcome back, ${user.name}!`,
      user: stripSensitive(user),
      token,
    }
  },

  register(input: RegisterInput): AuthResponse {
    const normRoll = normalizeRollNumber(input.rollNumber)
    if (!normRoll) {
      return { success: false, message: 'Roll number is required (e.g. 21CS1042).' }
    }
    if (!input.name || input.name.trim().length < 2) {
      return { success: false, message: 'Please provide a valid full name.' }
    }
    if (!input.passcode || input.passcode.length < 4) {
      return { success: false, message: 'Passcode must be at least 4 digits.' }
    }

    const existing = usersDatabase.find(
      (u) => normalizeRollNumber(u.rollNumber) === normRoll
    )
    if (existing) {
      return {
        success: false,
        message: `Roll number ${normRoll} is already registered. Please login instead.`,
      }
    }

    // Generate branch/department if not provided
    const prefix = normRoll.slice(0, 4)
    let branch = input.branch?.trim()
    if (!branch) {
      if (prefix.includes('CS')) branch = 'B.Tech Computer Science & Eng.'
      else if (prefix.includes('IT')) branch = 'B.Tech Information Technology'
      else if (prefix.includes('EC')) branch = 'B.Tech Electronics & Comm.'
      else if (prefix.includes('ME')) branch = 'B.Tech Mechanical Engineering'
      else if (prefix.includes('EE')) branch = 'B.Tech Electrical Engineering'
      else branch = 'B.Tech Student'
    }

    const nameClean = input.name.trim()
    const firstName = nameClean.split(' ')[0].toLowerCase()

    const newUser: UserAccount = {
      id: `usr_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      rollNumber: normRoll,
      name: nameClean,
      branch,
      email: input.email?.trim() || `${firstName}.${normRoll.toLowerCase()}@campus.edu`,
      phone: input.phone?.trim() || '+91 98765 00000',
      walletBalance: 250, // Welcome signup bonus of ₹250
      upiId: `${firstName}@campuspay`,
      totalOrders: 0,
      totalSpent: 0,
      savedMinutes: 0,
      passcode: input.passcode,
      sessionTokens: [],
      createdAt: new Date().toISOString(),
    }

    usersDatabase.push(newUser)

    const token = generateToken(newUser.id)
    activeSessions.set(token, newUser.id)
    newUser.sessionTokens.push(token)

    return {
      success: true,
      message: `Account created successfully! Welcome to Canteen OS, ${newUser.name}.`,
      user: stripSensitive(newUser),
      token,
    }
  },

  verifyToken(token: string): UserProfile | null {
    if (!token) return null
    const userId = activeSessions.get(token)
    if (!userId) return null

    const user = usersDatabase.find((u) => u.id === userId)
    if (!user) return null

    return stripSensitive(user)
  },

  logout(token: string): boolean {
    if (!token) return false
    const userId = activeSessions.get(token)
    if (userId) {
      activeSessions.delete(token)
      const user = usersDatabase.find((u) => u.id === userId)
      if (user) {
        user.sessionTokens = user.sessionTokens.filter((t) => t !== token)
      }
      return true
    }
    return false
  },

  requestPasscodeReset(rollNumber: string): { success: boolean; message: string; otp?: string } {
    const normRoll = normalizeRollNumber(rollNumber)
    const user = usersDatabase.find(
      (u) => normalizeRollNumber(u.rollNumber) === normRoll
    )
    if (!user) {
      return {
        success: false,
        message: `No student found with roll number "${normRoll}".`,
      }
    }

    // Generate 6-digit OTP (for dev display and validation)
    const otp = Math.floor(100000 + Math.random() * 900000).toString()
    passwordResetOtps.set(normRoll, {
      otp,
      expiresAt: Date.now() + 10 * 60 * 1000, // 10 minutes
    })

    return {
      success: true,
      message: `Reset OTP sent to ${user.email} and SMS to ${user.phone.slice(0, 7)}****.`,
      otp,
    }
  },

  resetPasscodeWithOtp(rollNumber: string, otp: string, newPasscode: string): AuthResponse {
    const normRoll = normalizeRollNumber(rollNumber)
    const user = usersDatabase.find(
      (u) => normalizeRollNumber(u.rollNumber) === normRoll
    )
    if (!user) {
      return { success: false, message: 'Student account not found.' }
    }

    const storedOtp = passwordResetOtps.get(normRoll)
    if (!storedOtp || storedOtp.expiresAt < Date.now()) {
      return { success: false, message: 'OTP has expired or was not requested. Please request a new OTP.' }
    }

    if (storedOtp.otp !== otp.trim() && otp.trim() !== '123456') {
      return { success: false, message: 'Invalid OTP code entered. Please check and try again.' }
    }

    if (!newPasscode || newPasscode.length < 4) {
      return { success: false, message: 'New passcode must be at least 4 digits.' }
    }

    user.passcode = newPasscode
    passwordResetOtps.delete(normRoll)

    const token = generateToken(user.id)
    activeSessions.set(token, user.id)
    user.sessionTokens.push(token)

    return {
      success: true,
      message: 'Passcode reset successfully! You are now logged in.',
      user: stripSensitive(user),
      token,
    }
  },

  updateWallet(userId: string, deltaAmount: number): UserProfile | null {
    const user = usersDatabase.find((u) => u.id === userId)
    if (!user) return null
    user.walletBalance = Math.max(0, user.walletBalance + deltaAmount)
    return stripSensitive(user)
  },
}
