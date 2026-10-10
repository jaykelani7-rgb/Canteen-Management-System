import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { apiClient, STUDENT_SESSION_EXPIRED } from '../../src/lib/apiClient'
import type { UserProfile, AuthResponse, RegisterInput, StudentMenuItem, StudentOrder, StudentOrderStatus, StudentNotification, OrderTracking, WalletTransaction, WalletTopup } from '../../src/lib/studentTypes'
import { checkoutIntent, clearCheckoutIntent, completeGatewayPayment, completeWalletTopup, walletTopupIntent, clearWalletTopupIntent, CheckoutDismissed } from '../../src/lib/paymentCheckout'
import './student.css'
import FoodImage from '../../src/components/FoodImage'
import FoodPhotoCredits from '../../src/components/FoodPhotoCredits'

/* ============================================================================
   Smart Canteen OS — Student Mobile App
   Separate mobile student application using the shared FastAPI backend.
   ========================================================================== */

/* ------------------------------- Data model ------------------------------- */

type Category = 'All' | StudentMenuItem['category']

type MenuItem = StudentMenuItem
type OrderStatus = StudentOrderStatus
type PastOrder = StudentOrder

/* ------------------------------ App context ------------------------------- */

type Screen =
  | 'login'
  | 'home'
  | 'menu'
  | 'details'
  | 'cart'
  | 'checkout'
  | 'confirm'
  | 'tracking'
  | 'ready'
  | 'history'
  | 'orderDetails'
  | 'notifications'
  | 'profile'
  | 'wallet'

type CartLine = { item: MenuItem; qty: number }

type Store = {
  go: (s: Screen) => void
  screen: Screen
  user: UserProfile | null
  menu: MenuItem[]
  orders: StudentOrder[]
  order: StudentOrder | null
  notifications: StudentNotification[]
  loading: boolean
  error: string | null
  menuLoading: boolean
  menuError: string | null
  menuCategory: Category
  setMenuCategory: (category: Category) => void
  refresh: () => Promise<void>
  selectOrder: (order: StudentOrder) => void
  submitOrder: (paymentMethod: string) => Promise<StudentOrder>
  completePayment: (order: StudentOrder) => Promise<StudentOrder>
  pickup: () => Promise<void>
  markRead: () => Promise<void>
  loginUser: (roll: string, passcode: string) => Promise<AuthResponse>
  registerUser: (input: RegisterInput) => Promise<AuthResponse>
  logoutUser: () => Promise<void>
  cart: CartLine[]
  add: (item: MenuItem, qty?: number) => void
  setQty: (id: string, qty: number) => void
  clear: () => void
  cartCount: number
  cartTotal: number
  selected: MenuItem | null
  select: (m: MenuItem | null) => void
  banner: SystemBanner | null
  setBanner: (b: SystemBanner | null) => void
  toast: string | null
  showToast: (msg: string) => void
}

type SystemBanner = 'offline' | 'reconnecting' | 'network'

const Ctx = createContext<Store>(null as unknown as Store)
const useStore = () => useContext(Ctx)

/* ------------------------------ Primitives -------------------------------- */

const rupee = (n: number | null | undefined) => `₹${Number(Number(n || 0).toFixed(2))}`
const campusTime = (value: string) => new Date(value).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })
const orderDate = (order: StudentOrder) => order.createdAt
  ? `${new Date(order.createdAt).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short' })} · ${campusTime(order.createdAt)}`
  : order.date

function Button({
  children,
  onClick,
  variant = 'primary',
  full,
  disabled,
  size = 'md',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost' | 'soft' | 'dark'
  full?: boolean
  disabled?: boolean
  size?: 'sm' | 'md'
}) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-2xl font-semibold transition-all active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100'
  const sizes = size === 'sm' ? 'px-4 py-2 text-sm' : 'px-5 py-3.5 text-[15px]'
  const variants: Record<string, string> = {
    primary:
      'bg-tangerine text-white shadow-[0_10px_24px_-8px_rgba(238,108,51,0.7)] hover:bg-tangerine-dark',
    dark: 'bg-ink text-white hover:opacity-90',
    soft: 'bg-tangerine-soft text-tangerine-dark hover:brightness-95',
    ghost: 'bg-transparent text-ink border border-line hover:bg-black/[0.03]',
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${sizes} ${variants[variant]} ${full ? 'w-full' : ''}`}
    >
      {children}
    </button>
  )
}

function StatusBadge({ status }: { status: OrderStatus }) {
  const map: Record<OrderStatus, { c: string; dot: string }> = {
    'Payment Pending': { c: 'bg-amber/15 text-[#a86b06]', dot: 'bg-amber' },
    Queued: { c: 'bg-slate-soft text-slate', dot: 'bg-slate' },
    Preparing: { c: 'bg-tangerine-soft text-tangerine-dark', dot: 'bg-tangerine' },
    Ready: { c: 'bg-mint-soft text-mint', dot: 'bg-mint' },
    'Picked Up': { c: 'bg-mint-soft text-mint', dot: 'bg-mint' },
    Completed: { c: 'bg-black/[0.05] text-ink-soft', dot: 'bg-ink-soft' },
    Delayed: { c: 'bg-amber/15 text-[#a86b06]', dot: 'bg-amber' },
    Cancelled: { c: 'bg-berry-soft text-berry', dot: 'bg-berry' },
  }
  const s = map[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${s.c}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${s.dot} ${status === 'Preparing' || status === 'Ready' ? '[animation:sco-pulse_1.4s_ease-in-out_infinite]' : ''}`}
      />
      {status}
    </span>
  )
}

function PaymentBadge({ status }: { status: PastOrder['payment'] }) {
  const map = {
    Pending: 'bg-amber/15 text-[#a86b06]',
    Paid: 'bg-mint-soft text-mint',
    Failed: 'bg-berry-soft text-berry',
    Refunded: 'bg-slate-soft text-slate',
  }
  return (
    <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${map[status]}`}>
      {status.toUpperCase()}
    </span>
  )
}

function QtyControl({
  qty,
  onChange,
  size = 'md',
}: {
  qty: number
  onChange: (q: number) => void
  size?: 'sm' | 'md'
}) {
  const btn =
    size === 'sm' ? 'h-7 w-7 text-base' : 'h-9 w-9 text-lg'
  return (
    <div className="inline-flex items-center gap-1 rounded-full bg-paper p-1">
      <button
        onClick={() => onChange(Math.max(0, qty - 1))}
        className={`${btn} grid place-items-center rounded-full bg-card font-bold text-ink shadow-sm active:scale-90`}
      >
        −
      </button>
      <span className="w-6 text-center font-mono text-sm font-bold">{qty}</span>
      <button
        onClick={() => onChange(qty + 1)}
        className={`${btn} grid place-items-center rounded-full bg-tangerine font-bold text-white shadow-sm active:scale-90`}
      >
        +
      </button>
    </div>
  )
}

function VegDot({ veg }: { veg: boolean }) {
  return (
    <span
      className={`grid h-3.5 w-3.5 place-items-center rounded-[3px] border ${veg ? 'border-mint' : 'border-berry'}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${veg ? 'bg-mint' : 'bg-berry'}`}
      />
    </span>
  )
}

function Icon({ name, className = '' }: { name: string; className?: string }) {
  const p: Record<string, ReactNode> = {
    home: <path d="M3 10.5 12 3l9 7.5M5 9.5V21h5v-6h4v6h5V9.5" />,
    menu: <path d="M4 6h16M4 12h16M4 18h10" />,
    bag: (
      <>
        <path d="M6 8h12l-1 12H7L6 8Z" />
        <path d="M9 8V6a3 3 0 0 1 6 0v2" />
      </>
    ),
    receipt: (
      <>
        <path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" />
        <path d="M9 8h6M9 12h6" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="3.5" />
        <path d="M5 20a7 7 0 0 1 14 0" />
      </>
    ),
    bell: (
      <>
        <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
        <path d="M10 20a2 2 0 0 0 4 0" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="6.5" />
        <path d="m20 20-3.5-3.5" />
      </>
    ),
    back: <path d="M15 5l-7 7 7 7" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3.5 2" />
      </>
    ),
    check: <path d="M4 12l5 5L20 6" />,
    pin: (
      <>
        <path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12Z" />
        <circle cx="12" cy="9" r="2.5" />
      </>
    ),
    flame: (
      <path d="M12 3s5 4 5 9a5 5 0 0 1-10 0c0-2 1-3 1-3s0 2 2 2c0-3 2-5 2-8Z" />
    ),
    star: (
      <path d="M12 3l2.6 5.6 6 .8-4.4 4.2 1.1 6L12 16.9 6.7 19.6l1.1-6L3.4 9.4l6-.8L12 3Z" />
    ),
    wifi: (
      <>
        <path d="M2 8.5a15 15 0 0 1 20 0M5 12a10 10 0 0 1 14 0M8 15.5a5 5 0 0 1 8 0" />
        <circle cx="12" cy="19" r="1" />
      </>
    ),
    off: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M6 6l12 12" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    chevron: <path d="M9 5l7 7-7 7" />,
    eye: (
      <>
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    eyeOff: (
      <>
        <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61M2 2l20 20" />
      </>
    ),
    lock: (
      <>
        <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </>
    ),
    sparkles: (
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
    ),
    x: <path d="M18 6 6 18M6 6l12 12" />,
    key: (
      <>
        <circle cx="7.5" cy="15.5" r="4.5" />
        <path d="m21 3-9.5 9.5M15.5 7.5l3 3M18.5 4.5l2 2" />
      </>
    ),
  }
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {p[name]}
    </svg>
  )
}

/* -------------------------- Layout scaffolding ---------------------------- */

function TopBar({
  title,
  onBack,
  right,
  subtitle,
}: {
  title: string
  onBack?: () => void
  right?: ReactNode
  subtitle?: string
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-3">
      {onBack && (
        <button
          onClick={onBack}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-card shadow-sm"
        >
          <Icon name="back" className="h-5 w-5" />
        </button>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-lg font-bold leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="truncate text-xs text-ink-soft">{subtitle}</p>
        )}
      </div>
      {right}
    </div>
  )
}

function BottomNav() {
  const { screen, go, cartCount } = useStore()
  const tabs: { key: Screen; label: string; icon: string }[] = [
    { key: 'home', label: 'Home', icon: 'home' },
    { key: 'menu', label: 'Menu', icon: 'menu' },
    { key: 'cart', label: 'Cart', icon: 'bag' },
    { key: 'history', label: 'Orders', icon: 'receipt' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ]
  const activeFor: Partial<Record<Screen, Screen>> = {
    details: 'menu',
    orderDetails: 'history',
    tracking: 'history',
    ready: 'history',
    confirm: 'history',
    checkout: 'cart',
    notifications: 'home',
  }
  const active = activeFor[screen] ?? screen
  return (
    <nav className="absolute inset-x-0 bottom-0 z-20 border-t border-line bg-card/95 px-2 pb-5 pt-2 backdrop-blur">
      <div className="flex items-end justify-around">
        {tabs.map((t) => {
          const on = active === t.key
          return (
            <button
              key={t.key}
              onClick={() => go(t.key)}
              className="relative flex flex-1 flex-col items-center gap-1 py-1"
            >
              <div className="relative">
                <Icon
                  name={t.icon}
                  className={`h-6 w-6 transition-colors ${on ? 'text-tangerine' : 'text-ink-soft'}`}
                />
                {t.key === 'cart' && cartCount > 0 && (
                  <span className="absolute -right-2 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-tangerine px-1 font-mono text-[10px] font-bold text-white">
                    {cartCount}
                  </span>
                )}
              </div>
              <span
                className={`text-[10px] font-semibold ${on ? 'text-tangerine' : 'text-ink-soft'}`}
              >
                {t.label}
              </span>
              {on && (
                <span className="absolute -top-2 h-1 w-1 rounded-full bg-tangerine" />
              )}
            </button>
          )
        })}
      </div>
    </nav>
  )
}

function Screen({
  children,
  nav = true,
  pad = true,
}: {
  children: ReactNode
  nav?: boolean
  pad?: boolean
}) {
  return (
    <div className="relative flex h-full min-h-0 flex-col bg-paper">
      <SystemBanners />
      <div
        className={`no-scrollbar flex-1 overflow-y-auto ${nav ? 'pb-24' : 'pb-6'} ${pad ? '' : ''}`}
      >
        {children}
      </div>
      {nav && <BottomNav />}
    </div>
  )
}

function SystemBanners() {
  const { banner, setBanner, refresh } = useStore()
  if (!banner) return null
  const cfg = {
    offline: { c: 'bg-ink text-white', t: 'You’re offline', s: 'Connect to the internet to place orders.', i: 'off' },
    reconnecting: { c: 'bg-amber text-ink', t: 'Reconnecting…', s: 'Trying to restore live updates.', i: 'wifi' },
    network: { c: 'bg-berry text-white', t: 'Network error', s: 'Couldn’t reach the canteen. Retry?', i: 'off' },
  }[banner]
  return (
    <div className={`mx-4 mb-1 flex items-center gap-3 rounded-2xl px-4 py-2.5 ${cfg.c} [animation:sco-rise_0.25s_ease]`}>
      <Icon
        name={cfg.i}
        className={`h-5 w-5 ${banner === 'reconnecting' ? '[animation:sco-pulse_1.2s_ease-in-out_infinite]' : ''}`}
      />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-bold leading-tight">{cfg.t}</p>
        <p className="truncate text-[11px] opacity-80">{cfg.s}</p>
      </div>
      {banner === 'network' && (
        <button onClick={() => { void refresh() }} className="rounded-lg bg-white/20 px-3 py-1 text-xs font-bold">
          Retry
        </button>
      )}
      <button onClick={() => setBanner(null)} className="text-lg leading-none opacity-70">
        ×
      </button>
    </div>
  )
}

function ToastBanner() {
  const { toast } = useStore()
  if (!toast) return null
  return (
    <div
      key={toast}
      role="status" aria-live="polite"
      className="pointer-events-none absolute bottom-28 left-1/2 z-50 -translate-x-1/2"
      style={{ animation: 'sco-toast-in 0.22s cubic-bezier(0.34,1.56,0.64,1) forwards' }}
    >
      <span className="flex items-center gap-2 whitespace-nowrap rounded-full bg-ink/92 px-5 py-2.5 text-sm font-semibold text-white shadow-2xl backdrop-blur">
        {toast}
      </span>
    </div>
  )
}

/* -------------------------------- Screens --------------------------------- */

function LoginScreen() {
  const { loginUser, registerUser, showToast, error: sessionError } = useStore()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [prefix] = useState('')
  const [rollNumber, setRollNumber] = useState('')
  const [passcode, setPasscode] = useState('')
  const [showPasscode, setShowPasscode] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Registration state
  const [regName, setRegName] = useState('')
  const [regRoll, setRegRoll] = useState('')
  const [regBranch, setRegBranch] = useState('B.Tech CSE')
  const [regPhone, setRegPhone] = useState('')
  const [regPasscode, setRegPasscode] = useState('')

  // Forgot Passcode state
  const [showForgotModal, setShowForgotModal] = useState(false)
  const [forgotRoll, setForgotRoll] = useState('')
  const [forgotStep, setForgotStep] = useState<'request' | 'reset'>('request')
  const [enteredOtp, setEnteredOtp] = useState('')
  const [newPasscode, setNewPasscode] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotError, setForgotError] = useState<string | null>(null)

  const handleLoginSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    setErrorMessage(null)
    const fullRoll = `${prefix}${rollNumber}`.trim()
    if (!rollNumber.trim()) {
      setErrorMessage('Please enter your roll digits.')
      return
    }
    if (!passcode) {
      setErrorMessage('Please enter your passcode.')
      return
    }

    setIsLoading(true)
    try {
      const res = await loginUser(fullRoll, passcode)
      if (!res.success) {
        setErrorMessage(res.message || 'Login failed. Please check credentials.')
      }
    } catch {
      setErrorMessage('Unable to connect to login backend.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRegisterSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    setErrorMessage(null)
    if (!regName.trim()) {
      setErrorMessage('Please enter your full name.')
      return
    }
    if (!regRoll.trim()) {
      setErrorMessage('Please enter your college roll number (e.g. 23CS1001).')
      return
    }
    if (!regPasscode || regPasscode.length < 4) {
      setErrorMessage('Passcode must be at least 4 digits.')
      return
    }

    setIsLoading(true)
    try {
      const res = await registerUser({
        name: regName,
        rollNumber: regRoll,
        branch: regBranch,
        phone: regPhone,
        passcode: regPasscode,
      })
      if (!res.success) {
        setErrorMessage(res.message || 'Registration failed.')
      }
    } catch {
      setErrorMessage('Failed to connect to registration backend.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRequestOtp = async () => {
    setForgotError(null)
    if (!forgotRoll.trim()) {
      setForgotError('Please enter your roll number.')
      return
    }
    setForgotLoading(true)
    try {
      const res = await apiClient.requestPasscodeReset(forgotRoll.trim())
      if (res.success) {
        setEnteredOtp('')
        setForgotStep('reset')
        showToast('Recovery request received. Follow the backend recovery instructions.')
      } else {
        setForgotError(res.message)
      }
    } catch (cause) {
      setForgotError((cause as Error).message)
    } finally {
      setForgotLoading(false)
    }
  }

  const handleResetPasscode = async () => {
    setForgotError(null)
    if (!enteredOtp.trim()) {
      setForgotError('Please enter the OTP.')
      return
    }
    if (!newPasscode || newPasscode.length < 4) {
      setForgotError('New passcode must be at least 4 digits.')
      return
    }
    setForgotLoading(true)
    try {
      const res = await apiClient.resetPasscode(forgotRoll.trim(), enteredOtp.trim(), newPasscode)
      if (res.success) {
        showToast(res.message || 'Passcode updated. Sign in again.')
        setShowForgotModal(false)
      } else {
        setForgotError(res.message)
      }
    } catch (cause) {
      setForgotError((cause as Error).message)
    } finally {
      setForgotLoading(false)
    }
  }

  return (
    <div className="relative flex h-full flex-col overflow-y-auto bg-ink text-white">
      <div
        className="absolute inset-0 opacity-40 pointer-events-none"
        style={{
          background:
            'radial-gradient(120% 80% at 80% -10%, rgba(238,108,51,0.9), transparent 55%), radial-gradient(90% 60% at 0% 20%, rgba(245,166,35,0.5), transparent 50%)',
        }}
      />

      <div className="relative flex flex-1 flex-col justify-between px-6 pb-6 pt-3">
        {/* Header Branding */}
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold backdrop-blur">
            <span className="text-base">🍔</span> Campus Canteen
          </div>
          <h1 className="font-display text-[34px] font-extrabold leading-[1.08] tracking-tight">
            Smart
            <br />
            Canteen <span className="text-amber">OS</span>
          </h1>
          <p className="mt-2 text-xs text-white/70">
            Order ahead, skip the line & grab food instantly.
          </p>
        </div>

        {/* Auth Card */}
        <div className="mt-4 rounded-3xl bg-white p-5 text-ink shadow-2xl">
          {/* Tabs */}
          <div className="mb-4 flex rounded-2xl bg-paper p-1">
            <button
              type="button"
              onClick={() => {
                setMode('login')
                setErrorMessage(null)
              }}
              className={`flex-1 rounded-xl py-2 text-xs font-bold transition-all ${
                mode === 'login'
                  ? 'bg-white text-ink shadow-sm'
                  : 'text-ink-soft hover:text-ink'
              }`}
            >
              Student Login
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('register')
                setErrorMessage(null)
              }}
              className={`flex-1 rounded-xl py-2 text-xs font-bold transition-all ${
                mode === 'register'
                  ? 'bg-white text-ink shadow-sm'
                  : 'text-ink-soft hover:text-ink'
              }`}
            >
              New Student ✨
            </button>
          </div>

          {(errorMessage || sessionError) && (
            <div className="mb-3.5 flex items-start gap-2 rounded-2xl bg-berry-soft p-3 text-xs text-berry">
              <span className="text-sm shrink-0">⚠️</span>
              <p className="leading-snug">{errorMessage || sessionError}</p>
            </div>
          )}

          {mode === 'login' ? (
            <form onSubmit={handleLoginSubmit}>
              {/* Roll number inputs */}
              <label className="block text-xs font-semibold text-ink-soft">
                College Roll ID
              </label>
              <div className="mt-1 flex items-center gap-2 rounded-2xl border border-line bg-paper px-3 py-2.5">
                <input
                  type="text"
                  value={rollNumber}
                  onChange={(e) => setRollNumber(e.target.value)}
                  placeholder="e.g. 21CS1042"
                  className="w-full bg-transparent font-mono text-sm font-semibold text-ink outline-none placeholder:text-ink-soft/50"
                />
              </div>

              {/* Passcode input */}
              <div className="mt-3 flex items-center justify-between">
                <label className="text-xs font-semibold text-ink-soft">
                  6-Digit Passcode
                </label>

              </div>
              <div className="mt-1 flex items-center gap-2 rounded-2xl border border-line bg-paper px-3 py-2.5">
                <Icon name="lock" className="h-4 w-4 text-ink-soft shrink-0" />
                <input
                  type={showPasscode ? 'text' : 'password'}
                  value={passcode}
                  onChange={(e) => setPasscode(e.target.value)}
                  placeholder="••••••"
                  className="w-full bg-transparent font-mono text-base tracking-[0.2em] font-bold text-ink outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPasscode(!showPasscode)}
                  className="text-ink-soft hover:text-ink p-1"
                >
                  <Icon name={showPasscode ? 'eyeOff' : 'eye'} className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-5">
                <Button full disabled={isLoading}>
                  {isLoading ? (
                    <div className="flex items-center gap-2">
                      <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                      <span>Authenticating…</span>
                    </div>
                  ) : (
                    'Log in →'
                  )}
                </Button>
              </div>

              <button
                type="button"
                onClick={() => {
                  setForgotRoll(`${prefix}${rollNumber}`)
                  setShowForgotModal(true)
                  setForgotStep('request')
                  setForgotError(null)
                }}
                className="mt-3 w-full text-center text-xs font-semibold text-ink-soft hover:text-ink"
              >
                Forgot passcode?
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegisterSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-ink-soft">
                  Student Full Name
                </label>
                <input
                  type="text"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="e.g. Aarav Sharma"
                  className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 text-sm font-semibold outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-semibold text-ink-soft">
                    Roll Number
                  </label>
                  <input
                    type="text"
                    value={regRoll}
                    onChange={(e) => setRegRoll(e.target.value)}
                    placeholder="23CS1055"
                    className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 font-mono text-sm font-semibold outline-none uppercase"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink-soft">
                    Department
                  </label>
                  <select
                    value={regBranch}
                    onChange={(e) => setRegBranch(e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-paper px-3 py-2.5 text-xs font-semibold outline-none"
                  >
                    <option value="B.Tech CSE">B.Tech CSE</option>
                    <option value="B.Tech IT">B.Tech IT</option>
                    <option value="B.Tech ECE">B.Tech ECE</option>
                    <option value="B.Tech Mech">B.Tech Mech</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink-soft">
                  Mobile Number (Optional)
                </label>
                <input
                  type="tel"
                  value={regPhone}
                  onChange={(e) => setRegPhone(e.target.value)}
                  placeholder="+91 98765 00000"
                  className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 text-sm font-semibold outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink-soft">
                  Create Passcode (4-6 digits)
                </label>
                <input
                  type="password"
                  value={regPasscode}
                  onChange={(e) => setRegPasscode(e.target.value)}
                  placeholder="Choose passcode"
                  className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 font-mono text-sm font-semibold outline-none"
                />
              </div>

              <div className="pt-2">
                <Button full disabled={isLoading}>
                  {isLoading ? (
                    <div className="flex items-center gap-2">
                      <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                      <span>Creating Account…</span>
                    </div>
                  ) : (
                    'Create student account'
                  )}
                </Button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* Forgot Passcode Modal */}
      {showForgotModal && (
        <div className="absolute inset-0 z-50 flex items-end bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full rounded-3xl bg-white p-5 text-ink shadow-2xl animate-in slide-in-from-bottom-5">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-xl bg-tangerine-soft text-tangerine-dark font-bold text-sm">
                  🔑
                </span>
                <h3 className="font-display text-base font-bold">Passcode Recovery</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowForgotModal(false)}
                className="grid h-7 w-7 place-items-center rounded-full bg-paper text-ink-soft hover:text-ink"
              >
                <Icon name="x" className="h-4 w-4" />
              </button>
            </div>

            {forgotError && (
              <div className="mt-3 rounded-xl bg-berry-soft p-2.5 text-xs text-berry">
                {forgotError}
              </div>
            )}

            {forgotStep === 'request' ? (
              <div className="mt-4 space-y-3">
                <p className="text-xs text-ink-soft">
                  Request recovery for your registered college roll number. Contact the canteen administrator if recovery is unavailable.
                </p>
                <div>
                  <label className="block text-xs font-semibold text-ink-soft">
                    Roll Number
                  </label>
                  <input
                    type="text"
                    value={forgotRoll}
                    onChange={(e) => setForgotRoll(e.target.value)}
                    placeholder="e.g. 21CS1042"
                    className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 font-mono text-sm font-bold uppercase outline-none"
                  />
                </div>
                <Button full onClick={handleRequestOtp} disabled={forgotLoading}>
                  {forgotLoading ? 'Sending OTP…' : 'Send Reset Code →'}
                </Button>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-ink-soft">
                    Enter OTP Code
                  </label>
                  <input
                    type="text"
                    value={enteredOtp}
                    onChange={(e) => setEnteredOtp(e.target.value)}
                    placeholder="6-digit OTP"
                    className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 font-mono text-sm font-bold tracking-widest outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink-soft">
                    New Passcode
                  </label>
                  <input
                    type="password"
                    value={newPasscode}
                    onChange={(e) => setNewPasscode(e.target.value)}
                    placeholder="Enter new 6-digit passcode"
                    className="mt-1 w-full rounded-2xl border border-line bg-paper px-3.5 py-2.5 font-mono text-sm font-bold outline-none"
                  />
                </div>
                <Button full onClick={handleResetPasscode} disabled={forgotLoading}>
                  {forgotLoading ? 'Updating…' : 'Set New Passcode & Login'}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function CategoryTabs({
  value,
  onChange,
}: {
  value: Category
  onChange: (c: Category) => void
}) {
  const cats: Category[] = ['All', 'Snacks', 'Meals', 'Beverages', 'Desserts', 'Quick Bites']
  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto px-5">
      {cats.map((c) => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
            value === c
              ? 'bg-ink text-white shadow-sm'
              : 'bg-card text-ink-soft'
          }`}
        >
          {c}
        </button>
      ))}
    </div>
  )
}

function SearchBar({ placeholder = 'Search the menu…' }) {
  const { go } = useStore()
  return (
    <div className="mx-5 flex items-center gap-3 rounded-2xl bg-card px-4 py-3 shadow-sm">
      <Icon name="search" className="h-5 w-5 text-ink-soft" />
      <input
        placeholder={placeholder}
        onFocus={() => go('menu')}
        className="w-full bg-transparent text-sm outline-none placeholder:text-ink-soft"
      />
    </div>
  )
}

function FoodCardWide({ item }: { item: MenuItem }) {
  const { add, select, go, cart, setQty } = useStore()
  const line = cart.find((l) => l.item.id === item.id)
  return (
    <div
      className={`relative flex gap-3 rounded-3xl bg-card p-3 shadow-[0_8px_24px_-16px_rgba(0,0,0,0.35)] ${item.available ? '' : 'opacity-100'}`}
    >
      <button
        onClick={() => {
          select(item)
          go('details')
        }}
        className="relative h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-paper"
      >
        <FoodImage
          src={item.photo}
          alt={item.name}
          className={`h-full w-full object-cover ${item.available ? '' : 'grayscale'}`}
        />
        {!item.available && (
          <div className="absolute inset-0 grid place-items-center bg-black/45 text-center text-[10px] font-bold uppercase tracking-wide text-white">
            Sold
            <br />
            out
          </div>
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-start gap-2">
          <VegDot veg={item.veg} />
          <button
            onClick={() => {
              select(item)
              go('details')
            }}
            className="min-w-0 flex-1 text-left"
          >
            <h3 className="truncate font-display text-[15px] font-bold leading-tight">
              {item.name}
            </h3>
          </button>
          {item.tag && (
            <span className="shrink-0 rounded-full bg-amber/15 px-2 py-0.5 text-[9px] font-bold text-[#a86b06]">
              {item.tag}
            </span>
          )}
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{item.desc}</p>
        <div className="mt-auto flex items-center justify-between pt-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[15px] font-bold">
              {rupee(item.price)}
            </span>
            <span className="flex items-center gap-0.5 text-[11px] font-semibold text-ink-soft">
              <Icon name="star" className="h-3 w-3 fill-amber text-amber" />
              {item.rating}
            </span>
          </div>
          {!item.available ? (
            <span className="text-[11px] font-bold text-berry">Unavailable</span>
          ) : line ? (
            <QtyControl
              qty={line.qty}
              onChange={(q) => setQty(item.id, q)}
              size="sm"
            />
          ) : (
            <button
              onClick={() => add(item)}
              className="flex items-center gap-1 rounded-full bg-tangerine-soft px-3 py-1.5 text-xs font-bold text-tangerine-dark active:scale-95"
            >
              <Icon name="plus" className="h-3.5 w-3.5" /> Add
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function HomeScreen() {
  const { go, user, menu: MENU, orders, selectOrder, notifications, menuLoading, menuError, refresh, setMenuCategory } = useStore()
  const firstName = user?.name ? user.name.split(' ')[0] : 'Student'
  const liveOrder = orders.find(o => !['Completed', 'Picked Up', 'Cancelled'].includes(o.status))
  const popular = [...MENU.filter(m => m.tag), ...MENU.filter(m => !m.tag)].slice(0, 4)
  return (
    <Screen>
      <div className="flex items-center justify-between px-5 pb-1 pt-1">
        <div>
          <p className="text-xs font-semibold text-ink-soft">Good afternoon 👋</p>
          <h1 className="font-display text-2xl font-extrabold leading-tight">
            Hey, {firstName}
          </h1>
          <div className="mt-1 flex items-center gap-1 text-xs text-ink-soft">
            <Icon name="pin" className="h-3.5 w-3.5 text-tangerine" />
            Main Block Canteen
          </div>
        </div>
        <button
          onClick={() => go('notifications')}
          className="relative grid h-11 w-11 place-items-center rounded-full bg-card shadow-sm"
        >
          <Icon name="bell" className="h-5 w-5" />
          {notifications.some(n => n.unread) && <span className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-tangerine ring-2 ring-card" />}
        </button>
      </div>

      <div className="mt-3">
        <SearchBar />
      </div>

      {menuLoading && menu.length === 0 && <p role="status" className="px-5 pt-4 text-sm text-ink-soft">Loading your canteen…</p>}
      {menuError && <div role="alert" className="mx-5 mt-4 rounded-2xl bg-berry-soft p-4 text-sm text-berry">{menuError}<button className="ml-3 font-bold" onClick={() => { void refresh() }}>Retry</button></div>}
      {liveOrder && <button onClick={() => { selectOrder(liveOrder); go(liveOrder.status === 'Ready' ? 'ready' : 'tracking') }} className="mx-5 mt-4 flex w-[calc(100%-2.5rem)] items-center gap-3 rounded-3xl bg-ink p-4 text-left text-white">
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-tangerine text-xl">🍔</div>
        <div className="flex-1"><p className="font-mono text-sm font-bold">{liveOrder.number}</p><p className="mt-1 text-xs text-white/70">Queue position {liveOrder.queuePosition} · Track →</p></div>
        <StatusBadge status={liveOrder.status} />
      </button>}

      {/* Categories quick */}
      <div className="mt-5 grid grid-cols-4 gap-2 px-5">
        {[
          { e: '🍟', l: 'Snacks' },
          { e: '🍜', l: 'Meals' },
          { e: '🥤', l: 'Beverages' },
          { e: '🔥', l: 'Quick Bites' },
        ].map((c) => (
          <button
            key={c.l}
            onClick={() => { setMenuCategory(c.l as Category); go('menu') }}
            className="flex flex-col items-center gap-1.5 rounded-2xl bg-card py-3 shadow-sm"
          >
            <span className="text-2xl">{c.e}</span>
            <span className="text-[11px] font-semibold">{c.l}</span>
          </button>
        ))}
      </div>

      {/* Promo */}
      <div className="mx-5 mt-5 flex items-center gap-4 overflow-hidden rounded-3xl bg-tangerine-soft p-5">
        <div className="flex-1">
          <p className="font-display text-lg font-bold text-tangerine-dark">
            Beat the 1 PM rush
          </p>
          <p className="mt-1 text-xs text-tangerine-dark/80">
            Pre-order now, we’ll hold your spot in the queue.
          </p>
          <button
            onClick={() => go('menu')}
            className="mt-3 rounded-full bg-tangerine px-4 py-2 text-xs font-bold text-white"
          >
            Order ahead
          </button>
        </div>
        <span className="text-5xl">⏱️</span>
      </div>

      <div className="mb-2 mt-6 flex items-center justify-between px-5">
        <h2 className="font-display text-lg font-bold">Popular today</h2>
        <button
          onClick={() => go('menu')}
          className="text-xs font-bold text-tangerine"
        >
          See all
        </button>
      </div>
      <div className="flex flex-col gap-3 px-5">
        {popular.map((m) => (
          <FoodCardWide key={m.id} item={m} />
        ))}
      </div>
    </Screen>
  )
}

function MenuScreen() {
  const { menu: MENU, menuLoading, menuError, refresh, menuCategory: cat, setMenuCategory: setCat } = useStore()
  const [query, setQuery] = useState('')
  const list = MENU.filter(
    (m) =>
      (cat === 'All' || m.category === cat) &&
      (query.trim() === '' || `${m.name} ${m.desc}`.toLowerCase().includes(query.trim().toLowerCase()))
  )
  return (
    <Screen>
      <TopBar title="Canteen Menu" subtitle={`${MENU.filter(m => m.available).length} items available · live`} />
      <div className="mx-5 flex items-center gap-3 rounded-2xl bg-card px-4 py-3 shadow-sm">
        <Icon name="search" className="h-5 w-5 text-ink-soft" />
        <input
          placeholder="Search the menu…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full bg-transparent text-sm outline-none placeholder:text-ink-soft"
        />
        {query && (
          <button onClick={() => setQuery('')} className="text-ink-soft text-lg leading-none">×</button>
        )}
      </div>
      <div className="mt-3">
        <CategoryTabs value={cat} onChange={setCat} />
      </div>
      <div className="mt-4 flex flex-col gap-3 px-5">
        {menuLoading && <p role="status" className="text-sm text-ink-soft">Loading fresh menu…</p>}
        {menuError && <p role="alert" className="text-sm text-berry">{menuError} <button onClick={() => { void refresh() }}>Retry</button></p>}
        {!menuLoading && !menuError && list.length === 0 ? (
          <EmptyState
            emoji="🔍"
            title={query.trim() ? 'No items found' : cat === 'All' ? 'Menu is being updated' : 'No items in this category'}
            body={query.trim() ? `Nothing matches "${query.trim()}". Try a different search.` : cat === 'All' ? 'Please refresh or check again shortly.' : `No ${cat.toLowerCase()} are available right now.`}
            cta={query.trim() ? 'Clear search' : cat === 'All' ? 'Refresh menu' : 'Show all items'}
            onCta={() => { setQuery(''); if (cat === 'All') { void refresh() } else setCat('All') }}
          />
        ) : (
          list.map((m) => <FoodCardWide key={m.id} item={m} />)
        )}
      </div>
    </Screen>
  )
}

function DetailsScreen() {
  const { selected, go, add, cart, setQty } = useStore()
  const item = selected
  const line = cart.find((l) => l.item.id === item?.id)
  const [qty, setLocalQty] = useState(line?.qty ?? 1)
  if (!item) return <Screen><TopBar title="Food details" onBack={() => go('menu')} /><EmptyState emoji="🍽️" title="Choose an item" body="Browse the menu to see food details." cta="Open menu" onCta={() => go('menu')} /></Screen>
  return (
    <Screen nav={false}>
      <div className="relative">
        <div className="relative h-64 w-full overflow-hidden bg-paper">
          <FoodImage
            src={item.photo}
            alt={item.name}
            className={`h-full w-full object-cover ${item.available ? '' : 'grayscale'}`}
          />
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-paper to-transparent" />
        </div>
        <button
          onClick={() => go('menu')}
          className="absolute left-5 top-2 grid h-10 w-10 place-items-center rounded-full bg-card shadow-md"
        >
          <Icon name="back" className="h-5 w-5" />
        </button>
      </div>

      <div className="-mt-4 px-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <VegDot veg={item.veg} />
              {item.tag && (
                <span className="rounded-full bg-amber/15 px-2 py-0.5 text-[10px] font-bold text-[#a86b06]">
                  {item.tag}
                </span>
              )}
            </div>
            <h1 className="font-display text-2xl font-extrabold leading-tight">
              {item.name}
            </h1>
          </div>
          <span className="font-mono text-2xl font-bold">
            {rupee(item.price)}
          </span>
        </div>

        <div className="mt-3 flex gap-2">
          <div className="flex items-center gap-1.5 rounded-full bg-card px-3 py-1.5 text-xs font-semibold shadow-sm">
            <Icon name="star" className="h-3.5 w-3.5 fill-amber text-amber" />
            {item.rating} rating
          </div>
          <div className="flex items-center gap-1.5 rounded-full bg-card px-3 py-1.5 text-xs font-semibold shadow-sm">
            <Icon name="clock" className="h-3.5 w-3.5 text-tangerine" />~
            {item.prepMins} min
          </div>
          <div className="flex items-center gap-1.5 rounded-full bg-card px-3 py-1.5 text-xs font-semibold shadow-sm">
            🔥 {item.calories == null ? 'Nutrition unavailable' : item.calories + ' kcal'}
          </div>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-ink-soft">{item.desc}</p>
        <FoodPhotoCredits url={item.photoCredits} />

        {item.available ? (
          <>
          </>
        ) : (
          <div className="mt-6 rounded-2xl border border-berry-soft bg-berry-soft p-4 text-center">
            <p className="font-display font-bold text-berry">
              Currently unavailable
            </p>
            <p className="mt-1 text-xs text-berry/80">
              This item is out of stock. Please check the menu again later.
            </p>
          </div>
        )}
      </div>

      {/* Sticky add bar */}
      <div className="sticky bottom-0 mt-6 flex items-center gap-3 border-t border-line bg-paper/95 px-5 py-4 backdrop-blur">
        {item.available ? (
          <>
            <QtyControl qty={qty} onChange={(q) => setLocalQty(Math.max(1, q))} />
            <div className="flex-1">
              <Button
                full
                onClick={() => {
                  if (line) setQty(item.id, qty)
                  else add(item, qty)
                  go('cart')
                }}
              >
                Add {qty} · {rupee(item.price * qty)}
              </Button>
            </div>
          </>
        ) : (
          <Button full variant="dark" onClick={() => go('menu')}>
            Back to menu
          </Button>
        )}
      </div>
    </Screen>
  )
}

function CartItemRow({ line }: { line: CartLine }) {
  const { setQty } = useStore()
  return (
    <div className="flex items-center gap-3 rounded-3xl bg-card p-3 shadow-sm">
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-2xl bg-paper">
        <FoodImage
          src={line.item.photo}
          alt={line.item.name}
          className="h-full w-full object-cover"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <VegDot veg={line.item.veg} />
          <h3 className="truncate font-display text-sm font-bold">
            {line.item.name}
          </h3>
        </div>
        <p className="mt-0.5 font-mono text-sm font-bold text-tangerine-dark">
          {rupee(line.item.price * line.qty)}
        </p>
      </div>
      <QtyControl qty={line.qty} onChange={(q) => setQty(line.item.id, q)} size="sm" />
    </div>
  )
}

function EmptyState({
  emoji,
  title,
  body,
  cta,
  onCta,
}: {
  emoji: string
  title: string
  body: string
  cta?: string
  onCta?: () => void
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-10 py-16 text-center">
      <div className="grid h-24 w-24 place-items-center rounded-3xl bg-card text-5xl shadow-sm">
        {emoji}
      </div>
      <h2 className="mt-5 font-display text-xl font-bold">{title}</h2>
      <p className="mt-2 text-sm text-ink-soft">{body}</p>
      {cta && (
        <div className="mt-6">
          <Button onClick={onCta}>{cta}</Button>
        </div>
      )}
    </div>
  )
}

function CartScreen() {
  const { cart, cartTotal, go } = useStore()
  const total = cartTotal
  return (
    <Screen>
      <TopBar title="Your Cart" subtitle={`${cart.length} item${cart.length !== 1 ? 's' : ''} · Main Block`} />
      {cart.length === 0 ? (
        <EmptyState
          emoji="🛒"
          title="Your cart is empty"
          body="Add some canteen favourites and beat the lunch rush."
          cta="Browse menu"
          onCta={() => go('menu')}
        />
      ) : (
        <>
          <div className="flex flex-col gap-3 px-5">
            {cart.map((l) => (
              <CartItemRow key={l.item.id} line={l} />
            ))}
          </div>

          <div className="mx-5 mt-4 rounded-3xl bg-card p-5 shadow-sm">
            <h3 className="font-display text-sm font-bold">Bill details</h3>
            <div className="mt-3 flex flex-col gap-2 text-sm">
              <Row l="Item total" v={rupee(cartTotal)} />
              <div className="my-1 border-t border-dashed border-line" />
              <Row l="To pay" v={rupee(total)} bold />
            </div>
          </div>
        </>
      )}

      {cart.length > 0 && (
        <div className="sticky bottom-0 mt-5 flex items-center gap-4 border-t border-line bg-paper/95 px-5 py-4 backdrop-blur">
          <div>
            <p className="text-[11px] text-ink-soft">Total</p>
            <p className="font-mono text-lg font-bold">{rupee(total)}</p>
          </div>
          <div className="flex-1">
            <Button full onClick={() => go('checkout')}>
              Checkout →
            </Button>
          </div>
        </div>
      )}
    </Screen>
  )
}

function Row({ l, v, bold }: { l: string; v: string; bold?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className={bold ? 'font-bold' : 'text-ink-soft'}>{l}</span>
      <span className={`font-mono ${bold ? 'text-base font-bold' : 'font-semibold'}`}>
        {v}
      </span>
    </div>
  )
}

function CheckoutScreen() {
  const { cart, cartTotal, go, submitOrder, user } = useStore()
  const [pay, setPay] = useState('wallet')
  const [gatewayEnabled, setGatewayEnabled] = useState(false)
  const [configError, setConfigError] = useState('')
  useEffect(() => { let active = true; apiClient.getPaymentsConfig().then(config => { if (active) setGatewayEnabled(config.enabled && config.provider === 'razorpay') }).catch(cause => { if (active) setConfigError((cause as Error).message) }); return () => { active = false } }, [])
  const [failed, setFailed] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [unconfirmed, setUnconfirmed] = useState(false)
  const submitLock = useRef(false)
  const placeOrder = async () => {
    if (submitLock.current || !cart.length) return
    submitLock.current = true; setSubmitting(true); setFailed(null)
    try { const placed = await submitOrder(pay); go(placed.payment === 'Paid' ? 'confirm' : 'tracking') }
    catch (e) { setFailed((e as Error).message); if ((e as { status?: number }).status === 0) setUnconfirmed(true) }
    finally { submitLock.current = false; setSubmitting(false) }
  }
  const total = cartTotal
  return (
    <Screen nav={false}>
      <TopBar title="Checkout" onBack={() => go('cart')} />
      <div className="px-5">
        {failed && (
          <div className="mb-4 flex items-start gap-3 rounded-2xl bg-berry-soft p-4 [animation:sco-rise_0.25s_ease]">
            <span className="text-xl">⚠️</span>
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-berry">
                Order could not be confirmed
              </p>
              <p className="mt-0.5 text-xs text-berry/80">
                {failed}
              </p>
            </div>

          </div>
        )}

        {/* Pickup */}
        <h3 className="font-display text-sm font-bold">Pickup details</h3>
        <div className="mt-2 rounded-3xl bg-card p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <Icon name="pin" className="h-5 w-5 text-tangerine" />
            <div className="flex-1">
              <p className="text-sm font-bold">Main Block Canteen</p>
              <p className="text-xs text-ink-soft">Counter assigned after ordering · Self pickup</p>
            </div>
            <span className="rounded-full bg-mint-soft px-2.5 py-1 text-[11px] font-bold text-mint">
              Self pickup
            </span>
          </div>
          <div className="mt-3 flex items-center gap-3 border-t border-line pt-3">
            <Icon name="clock" className="h-5 w-5 text-tangerine" />
            <div className="flex-1">
              <p className="text-sm font-bold">As soon as possible</p>
              <p className="text-xs text-ink-soft">
                Ready time will be confirmed after ordering
              </p>
            </div>
          </div>
        </div>

        {configError && <p role="alert" className="mt-4 text-xs text-berry">{configError}</p>}
        {/* Payment methods */}
        <h3 className="mt-6 font-display text-sm font-bold">Payment method</h3>
        <div className="mt-2 flex flex-col gap-2">
          {[
            { id: 'upi', l: 'Campus UPI', s: gatewayEnabled ? 'Secure checkout through Razorpay' : 'Online payments unavailable', e: '🟣' },
            { id: 'wallet', l: 'Canteen Wallet', s: `Balance ₹${user?.walletBalance ?? 0}`, e: '👛' },
            { id: 'card', l: 'Card', s: gatewayEnabled ? 'Secure checkout through Razorpay' : 'Online payments unavailable', e: '💳' },
          ].map((p) => (
            <button
              key={p.id}
              onClick={() => setPay(p.id)}
              disabled={submitting || (p.id !== 'wallet' && !gatewayEnabled)}
              className={`flex items-center gap-3 rounded-2xl border-2 bg-card px-4 py-3 text-left transition-colors ${pay === p.id ? 'border-tangerine' : 'border-transparent'}`}
            >
              <span className="text-xl">{p.e}</span>
              <div className="flex-1">
                <p className="text-sm font-bold">{p.l}</p>
                <p className="text-xs text-ink-soft">{p.s}</p>
              </div>
              <span
                className={`grid h-5 w-5 place-items-center rounded-full border-2 ${pay === p.id ? 'border-tangerine bg-tangerine' : 'border-line'}`}
              >
                {pay === p.id && (
                  <Icon name="check" className="h-3 w-3 text-white" />
                )}
              </span>
            </button>
          ))}
        </div>

        <div className="mt-6 rounded-3xl bg-card p-5 shadow-sm">
          <div className="flex flex-col gap-2 text-sm">
            <Row l={`Items (${cart.length})`} v={rupee(cartTotal)} />
            <div className="my-1 border-t border-dashed border-line" />
            <Row l="To pay" v={rupee(total)} bold />
          </div>
        </div>
      </div>

      <div className="sticky bottom-0 mt-6 flex flex-col gap-2 border-t border-line bg-paper/95 px-5 py-4 backdrop-blur">
        <Button
          full
          disabled={submitting || unconfirmed || !cart.length || (pay !== 'wallet' && !gatewayEnabled)}
          onClick={() => { void placeOrder() }}
        >
          {submitting ? 'Placing order…' : unconfirmed ? 'Check Your Orders before trying again' : `Pay ${rupee(total)} & place order`}
        </Button>
        {unconfirmed && <Button full variant="ghost" onClick={() => go('history')}>Check Your Orders</Button>}
      </div>
    </Screen>
  )
}

function ConfirmScreen() {
  const { go, order } = useStore()
  if (!order) return <Screen><TopBar title="Order confirmation" /><EmptyState emoji="🧾" title="No confirmed order" body="Place an order from your cart." cta="Your orders" onCta={() => go('history')} /></Screen>
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-paper">
      <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        <div className="relative">
          <span className="absolute inset-0 rounded-full bg-mint/30 [animation:sco-ping_1.6s_ease-out_infinite]" />
          <div className="relative grid h-24 w-24 place-items-center rounded-full bg-mint text-white">
            <Icon name="check" className="h-12 w-12" />
          </div>
        </div>
        <h1 className="mt-7 font-display text-3xl font-extrabold">
          Order placed!
        </h1>
        <p className="mt-2 max-w-xs text-sm text-ink-soft">
          Your food is now in the queue. Track your position and ready time live.
        </p>

        <div className="mt-7 w-full rounded-3xl border border-line bg-card p-6 shadow-sm">
          <p className="text-xs font-semibold text-ink-soft">Your order number</p>
          <p className="mt-1 font-mono text-4xl font-bold tracking-tight text-tangerine">
            {order.number}
          </p>
          <div className="mt-4 flex items-center justify-center gap-6 border-t border-dashed border-line pt-4">
            <div>
              <p className="font-mono text-lg font-bold">{order.queuePosition}</p>
              <p className="text-[11px] text-ink-soft">Queue pos.</p>
            </div>
            <div className="h-8 w-px bg-line" />
            <div>
              <p className="font-mono text-lg font-bold text-tangerine">{order.prepTimeMinutes} min</p>
              <p className="text-[11px] text-ink-soft">Ready in</p>
            </div>
            <div className="h-8 w-px bg-line" />
            <div>
              <p className="font-mono text-lg font-bold">{order.estimatedReadyAt ? campusTime(order.estimatedReadyAt) : 'Pending'}</p>
              <p className="text-[11px] text-ink-soft">Ready by</p>
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2 px-6 pb-8">
        <Button full onClick={() => go('tracking')}>
          Track my order live →
        </Button>
        <Button variant="ghost" full onClick={() => go('home')}>
          Back to home
        </Button>
      </div>
    </div>
  )
}

/* ---- The hero screen: Live Order Tracking ---- */

function TrackingScreen() {
  const { go, order, selectOrder, completePayment, showToast } = useStore()
  const [paying, setPaying] = useState(false)
  const paymentLock = useRef(false)
  const [tracking, setTracking] = useState<OrderTracking | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!order) return
    let active = true
    let inFlight = false
    const load = async () => {
      if (inFlight || paymentLock.current) return
      inFlight = true
      try {
        const [next, current] = await Promise.all([apiClient.getTracking(order.orderId), apiClient.getOrder(order.orderId)])
        if (!active) return
        setTracking(next); setError(null); selectOrder(current)
      } catch (e) { if (active) setError((e as Error).message) }
      finally { inFlight = false }
    }
    void load(); const timer = setInterval(() => { if (document.visibilityState === 'visible') void load() }, 5000)
    return () => { active = false; clearInterval(timer) }
  }, [order?.orderId])
  if (!order) return <Screen><TopBar title="Live Order Tracking" /><EmptyState emoji="🧾" title="Select an order" body="Open Your Orders to track a current order." cta="Your Orders" onCta={() => go('history')} /></Screen>
  const status = order.status === 'Payment Pending' ? order.status : tracking?.status ?? order.status
  const resumePayment = async () => { if (paymentLock.current) return; paymentLock.current = true; setPaying(true); try { const result = await completePayment(order); if (result.payment === 'Paid') go('confirm'); else showToast('Payment is awaiting confirmation. We will keep checking.') } catch (cause) { showToast((cause as Error).message) } finally { paymentLock.current = false; setPaying(false) } }
  return <Screen>
    <TopBar title="Live Order Tracking" onBack={() => go('home')} right={<StatusBadge status={status} />} />
    {error && <p role="alert" className="mx-5 mb-4 rounded-2xl bg-berry-soft p-3 text-sm text-berry">{error} · Retrying automatically</p>}
    {order.refundStatus && <p role="status" className="mx-5 mb-4 rounded-2xl bg-card p-4 text-sm shadow-sm">Refund status: <strong>{order.refundStatus.replace(/_/g, ' ')}</strong>. Refund completion is confirmed by the payment provider.</p>}
    {status === 'Payment Pending' && <div className="mx-5 mb-4 rounded-3xl bg-card p-5 shadow-sm"><p className="text-sm font-bold">Awaiting payment confirmation</p><p className="mt-1 text-xs text-ink-soft">Food preparation starts after the backend confirms payment.</p>{order.checkout && <div className="mt-3"><Button full disabled={paying} onClick={() => { void resumePayment() }}>{paying ? 'Opening secure payment…' : 'Complete payment'}</Button></div>}</div>}
    <div className="mx-5 overflow-hidden rounded-3xl bg-ink p-6 text-white">
      <div className="flex items-center justify-between"><div><p className="text-xs text-white/60">Order number</p><p className="font-mono text-2xl font-bold">{order.number}</p></div><StatusBadge status={status} /></div>
      <div className="mt-6 text-center"><p className="text-xs uppercase tracking-widest text-white/50">{status === 'Payment Pending' ? 'Awaiting payment' : status === 'Ready' ? 'Ready for pickup' : ['Cancelled','Completed','Picked Up'].includes(status) ? status : 'Ready in about'}</p><p className="mt-1 font-mono text-6xl font-bold text-amber">{status === 'Payment Pending' ? '—' : tracking?.countdownMinutesFormatted ?? '…'}</p><p className="mt-2 text-xs text-white/60">Expected ready time · {order.estimatedReadyAt ? campusTime(order.estimatedReadyAt) : tracking?.estimatedReadyTime ?? 'Updating…'}</p></div>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/15"><div className="h-full rounded-full bg-tangerine transition-all" style={{ width: `${tracking?.progressPercent ?? 0}%` }} /></div>
    </div>
    <div className="mt-4 grid grid-cols-2 gap-3 px-5"><div className="rounded-3xl bg-card p-4 shadow-sm"><p className="text-xs text-ink-soft">Queue position</p><p className="mt-1 font-mono text-3xl font-bold text-tangerine">#{status === 'Payment Pending' ? '—' : tracking?.queuePosition ?? order.queuePosition}</p></div><div className="rounded-3xl bg-card p-4 shadow-sm"><p className="text-xs text-ink-soft">Orders ahead</p><p className="mt-1 font-mono text-3xl font-bold">{tracking?.ordersAhead ?? '…'}</p></div></div>
    <div className="mx-5 mt-5 rounded-3xl bg-card p-5 shadow-sm"><h3 className="mb-4 font-display text-sm font-bold">Order timeline</h3>{tracking?.timeline.map(step => <div key={step.key} className="flex gap-4 pb-5 last:pb-0"><div className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${step.done ? 'bg-mint text-white' : step.active ? 'bg-tangerine text-white' : 'bg-paper text-ink-soft'}`}>{step.done ? '✓' : '•'}</div><div><p className={`text-sm font-bold ${step.active ? 'text-tangerine' : ''}`}>{step.label}</p><p className="text-[11px] text-ink-soft">{step.note}</p></div></div>)}</div>
    <div className="mx-5 mt-4 flex gap-3">{status === 'Ready' && <Button full onClick={() => go('ready')}>Show pickup token</Button>}<Button variant="ghost" full onClick={() => go('history')}>Your orders</Button></div>
  </Screen>
}

function ReadyScreen() {
  const { go, order, pickup, showToast } = useStore()
  const [busy, setBusy] = useState(false)
  if (!order || order.status !== 'Ready') return <Screen><TopBar title="Pickup" /><EmptyState emoji="🍽️" title="Your order is not ready" body="The kitchen will notify you when food is ready." cta="Track order" onCta={() => go('tracking')} /></Screen>
  const collect = async () => { if (busy) return; setBusy(true); try { await pickup(); go('history') } catch(e) { showToast((e as Error).message) } finally { setBusy(false) } }
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-mint text-white">
      <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        <div className="relative">
          <span className="absolute inset-0 rounded-full bg-white/40 [animation:sco-ping_1.8s_ease-out_infinite]" />
          <div className="relative grid h-28 w-28 place-items-center rounded-full bg-white text-6xl">
            🔔
          </div>
        </div>
        <p className="mt-8 text-sm font-semibold uppercase tracking-widest text-white/80">
          Order {order.number}
        </p>
        <h1 className="mt-2 font-display text-4xl font-extrabold">
          Your food is ready!
        </h1>
        <p className="mt-3 max-w-xs text-sm text-white/85">
          Head to <b>{order.pickupCounter}</b> at the Main Block Canteen and show this
          screen to collect your order.
        </p>

        <div className="mt-8 w-full rounded-3xl bg-white/15 p-5 backdrop-blur">
          <div className="flex items-center justify-center gap-8">
            <div>
              <p className="font-mono text-3xl font-bold">{order.pickupCounter}</p>
              <p className="text-[11px] text-white/70">Counter</p>
            </div>
            <div className="h-10 w-px bg-white/30" />
            <div>
              <p className="font-mono text-3xl font-bold">{order.pickupToken}</p>
              <p className="text-[11px] text-white/70">Show at pickup</p>
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2 px-6 pb-8">
        <button
          disabled={busy} onClick={() => { void collect() }}
          className="w-full rounded-2xl bg-white py-3.5 font-semibold text-mint active:scale-[0.98]"
        >
          {busy ? 'Confirming…' : 'Mark as picked up'}
        </button>
        <button
          onClick={() => go('tracking')}
          className="w-full rounded-2xl bg-white/15 py-3 text-sm font-semibold text-white"
        >
          Back to tracking
        </button>
      </div>
    </div>
  )
}

function OrderCard({ order }: { order: PastOrder }) {
  const { go, selectOrder } = useStore()
  const live = !['Completed', 'Cancelled', 'Picked Up'].includes(order.status)
  return (
    <button
      onClick={() => { selectOrder(order); go(order.status === 'Ready' ? 'ready' : live ? 'tracking' : 'orderDetails') }}
      className="w-full rounded-3xl bg-card p-4 text-left shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold">{order.number}</span>
          <PaymentBadge status={order.payment} />
        </div>
        <StatusBadge status={order.status === 'Preparing' ? 'Preparing' : order.status} />
      </div>
      <p className="mt-2 truncate text-sm text-ink-soft">
        {order.items.map((i) => `${i.qty}× ${i.name}`).join(', ')}
      </p>
      <div className="mt-3 flex items-center justify-between border-t border-dashed border-line pt-3">
        <span className="text-xs text-ink-soft">{orderDate(order)}</span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold">{rupee(order.total)}</span>
          <span className="text-xs font-bold text-tangerine">
            {live ? 'Track →' : 'Details →'}
          </span>
        </div>
      </div>
    </button>
  )
}

function HistoryScreen() {
  const { orders: HISTORY, go, refresh, error, loading } = useStore()
  const [tab, setTab] = useState<'active' | 'past'>('active')
  const active = HISTORY.filter(
    (o) => !['Completed', 'Cancelled', 'Picked Up'].includes(o.status)
  )
  const past = HISTORY.filter(
    (o) => ['Completed', 'Cancelled', 'Picked Up'].includes(o.status)
  )
  const list = tab === 'active' ? active : past
  return (
    <Screen>
      <TopBar title="Your Orders" right={<button className="text-xs font-bold text-tangerine" onClick={() => { void refresh() }}>Refresh</button>} />
      {loading && <p className="px-5 text-sm text-ink-soft">Loading orders…</p>}
      {error && <p className="px-5 text-sm text-berry">{error}</p>}
      <div className="mx-5 flex gap-1 rounded-2xl bg-card p-1 shadow-sm">
        {(['active', 'past'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-xl py-2 text-sm font-bold capitalize transition-colors ${
              tab === t ? 'bg-ink text-white' : 'text-ink-soft'
            }`}
          >
            {t === 'active' ? 'Active' : 'History'}
          </button>
        ))}
      </div>

      {list.length === 0 ? (
        <EmptyState
          emoji="🧾"
          title={tab === 'active' ? 'No active orders' : 'No past orders yet'}
          body={
            tab === 'active'
              ? 'When you place an order, it’ll show here with live tracking.'
              : 'Your completed and cancelled orders will appear here.'
          }
          cta="Order something"
          onCta={() => go('menu')}
        />
      ) : (
        <div className="mt-4 flex flex-col gap-3 px-5">
          {list.map((o) => (
            <OrderCard key={o.id} order={o} />
          ))}
        </div>
      )}
    </Screen>
  )
}

function OrderDetailsScreen() {
  const { go, order: o, menu: MENU } = useStore()
  if (!o) return <Screen><TopBar title="Order details" /><EmptyState emoji="🧾" title="Select an order" body="Choose an order from Your Orders." cta="Your orders" onCta={() => go('history')} /></Screen>
  return (
    <Screen nav={false}>
      <TopBar
        title={`Order ${o.number}`}
        subtitle={orderDate(o)}
        onBack={() => go('history')}
        right={<StatusBadge status={o.status} />}
      />
      <div className="px-5">
        <div className="rounded-3xl bg-card p-5 shadow-sm">
          <h3 className="font-display text-sm font-bold">Items</h3>
          <div className="mt-3 flex flex-col gap-3">
            {o.items.map((it) => {
              const m = MENU.find((x) => x.id === it.id)
              return (
                <div key={it.name} className="flex items-center gap-3">
                  <div className="h-12 w-12 overflow-hidden rounded-xl bg-paper">
                    <FoodImage src={it.photo || m?.photo} alt={it.name} className="h-full w-full object-cover" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-bold">{it.name}</p>
                    <p className="text-xs text-ink-soft">Qty {it.qty}</p>
                  </div>
                  <span className="font-mono text-sm font-semibold">
                    {rupee(it.price * it.qty)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        <div className="mt-4 rounded-3xl bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-sm font-bold">Payment</h3>
            <PaymentBadge status={o.payment} />
          </div>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <Row l="Item total" v={rupee(o.itemTotal)} />
            {o.packagingFee + o.gst > 0 && <Row l="Taxes & packaging" v={rupee(o.packagingFee + o.gst)} />}
            <Row l="Paid via" v={o.paymentMethod} />
            {o.refundStatus && <Row l="Refund status" v={o.refundStatus.replace(/_/g, ' ')} />}
            {o.cancellationReason && <p className="text-xs text-ink-soft">Cancellation: {o.cancellationReason}</p>}
            <div className="my-1 border-t border-dashed border-line" />
            <Row l={o.payment === 'Pending' ? 'Payment pending' : 'Total paid'} v={rupee(o.payment === 'Paid' || o.payment === 'Refunded' ? o.total : 0)} bold />
          </div>
        </div>

        <div className="mt-4 rounded-3xl bg-card p-5 shadow-sm">
          <h3 className="font-display text-sm font-bold">Pickup</h3>
          <div className="mt-3 flex items-center gap-3">
            <Icon name="pin" className="h-5 w-5 text-tangerine" />
            <div>
              <p className="text-sm font-bold">Main Block Canteen · {o.pickupCounter}</p>
              <p className="text-xs text-ink-soft">{o.completedAt ? `Collected at ${new Date(o.completedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : `Pickup token ${o.pickupToken}`} </p>
            </div>
          </div>
        </div>

        <div className="mt-5 flex gap-3">
          <Button variant="ghost" full onClick={() => go('menu')}>
            Reorder
          </Button>

        </div>
      </div>
    </Screen>
  )
}

function NotificationsScreen() {
  const { go, notifications, markRead, showToast } = useStore()
  const notes = notifications.map(n => ({ e: n.emoji, c: n.color, t: n.title, s: n.subtitle, time: n.time, unread: n.unread }))
  const color: Record<string, string> = {
    mint: 'bg-mint-soft',
    tangerine: 'bg-tangerine-soft',
    slate: 'bg-slate-soft',
    amber: 'bg-amber/15',
    berry: 'bg-berry-soft',
  }
  return (
    <Screen>
      <TopBar
        title="Notifications"
        onBack={() => go('home')}
        right={
          <button onClick={() => { void markRead().catch(e => showToast((e as Error).message)) }} className="text-xs font-bold text-tangerine">
            Mark all read
          </button>
        }
      />
      <div className="flex flex-col gap-2 px-5">
        {!notes.length && <EmptyState emoji="🔔" title="No notifications" body="Your order updates will appear here." cta="Browse menu" onCta={() => go('menu')} />}
        {notes.map((n, i) => (
          <div
            key={i}
            className={`flex gap-3 rounded-2xl p-3.5 ${n.unread ? 'bg-card shadow-sm' : 'bg-transparent'}`}
          >
            <div
              className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-xl ${color[n.c]}`}
            >
              {n.e}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-bold leading-tight">{n.t}</p>
                {n.unread && (
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-tangerine" />
                )}
              </div>
              <p className="mt-0.5 text-xs text-ink-soft">{n.s}</p>
              <p className="mt-1 text-[10px] font-semibold text-ink-soft">
                {n.time}
              </p>
            </div>
          </div>
        ))}
      </div>
    </Screen>
  )
}

function ProfileScreen() {
  const { go, user, orders, logoutUser } = useStore()
  const initial = user?.name ? user.name.charAt(0) : 'A'
  const fullName = user?.name || 'Student'
  const roll = user?.rollNumber || ''
  const branch = user?.branch || ''
  const walletBal = user?.walletBalance ?? 0
  const totalOrders = user?.totalOrders ?? 0
  const totalSpent = rupee(user?.totalSpent ?? 0)
  const activeOrders = orders.filter(row => !['Completed', 'Picked Up', 'Cancelled'].includes(row.status)).length

  return (
    <Screen>
      <TopBar title="Profile" />
      <div className="px-5">
        <div className="flex items-center gap-4 rounded-3xl bg-ink p-5 text-white">
          <div className="grid h-16 w-16 place-items-center rounded-2xl bg-tangerine font-display text-2xl font-bold">
            {initial}
          </div>
          <div className="flex-1">
            <h2 className="font-display text-xl font-bold">{fullName}</h2>
            <p className="text-xs text-white/60">{roll} · {branch}</p>
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold">
              👛 Wallet ₹{walletBal}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            { n: `${totalOrders}`, l: 'Orders' },
            { n: `${totalSpent}`, l: 'Spent' },
            { n: `${activeOrders}`, l: 'Active orders' },
          ].map((s) => (
            <div
              key={s.l}
              className="rounded-2xl bg-card p-3 text-center shadow-sm"
            >
              <p className="font-mono text-lg font-bold">{s.n}</p>
              <p className="text-[11px] text-ink-soft">{s.l}</p>
            </div>
          ))}
        </div>

        <div className="mt-5 overflow-hidden rounded-3xl bg-card shadow-sm">
          {[
            { i: '🧾', l: 'Order history', s: () => go('history') },
            { i: '🔔', l: 'Notifications', s: () => go('notifications') },
            { i: '👛', l: 'Canteen wallet', s: () => go('wallet') },
          ].map((r, i, arr) => (
            <button
              key={r.l}
              onClick={r.s}
              className={`flex w-full items-center gap-3 px-4 py-3.5 text-left ${i < arr.length - 1 ? 'border-b border-line' : ''}`}
            >
              <span className="text-lg">{r.i}</span>
              <span className="flex-1 text-sm font-semibold">{r.l}</span>
              <Icon name="chevron" className="h-4 w-4 text-ink-soft" />
            </button>
          ))}
        </div>

        <div className="mt-5">
          <Button
            variant="ghost"
            full
            onClick={async () => {
              await logoutUser()
            }}
          >
            Log out
          </Button>
        </div>
      </div>
    </Screen>
  )
}

function WalletScreen() {
  const { go, user, refresh, showToast } = useStore()
  const [transactions, setTransactions] = useState<WalletTransaction[]>([])
  const [topups, setTopups] = useState<WalletTopup[]>([])
  const [walletBalance, setWalletBalance] = useState<number | null>(null)
  const [amount, setAmount] = useState('500')
  const [gatewayEnabled, setGatewayEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const busy = useRef(false)
  const alive = useRef(true)
  const revision = useRef(0)
  const reload = useRef<() => Promise<void>>(async () => {})
  const refreshRef = useRef(refresh); refreshRef.current = refresh
  useEffect(() => {
    let active = true, inFlight = false
    alive.current = true
    const load = async () => {
      if (inFlight || busy.current) return
      inFlight = true
      const requestedRevision = revision.current
      try {
        const results = await Promise.allSettled([apiClient.getWallet(), apiClient.getWalletTransactions(), apiClient.getWalletTopups(), apiClient.getPaymentsConfig()])
        if (!active || requestedRevision !== revision.current) return
        const [wallet, ledger, payments, config] = results
        if (wallet.status === 'fulfilled') setWalletBalance(wallet.value.walletBalance)
        if (ledger.status === 'fulfilled') setTransactions(ledger.value)
        if (payments.status === 'fulfilled') setTopups(payments.value)
        if (config.status === 'fulfilled') setGatewayEnabled(config.value.enabled && config.value.provider === 'razorpay')
        const failed = results.find(result => result.status === 'rejected')
        setError(failed?.status === 'rejected' ? (failed.reason as Error).message : null)
      } finally { inFlight = false; if (active) setLoading(false) }
    }
    reload.current = load
    void load(); void refreshRef.current()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load() }, 10000)
    return () => { active = false; alive.current = false; clearInterval(timer) }
  }, [user?.id])
  const rememberTopup = (next: WalletTopup) => {
    if (!alive.current) return
    setTopups(prev => [next, ...prev.filter(row => row.id !== next.id)])
    // The backend returns the actual balance; the browser never calculates a credit.
    if (next.state === 'captured') setWalletBalance(next.walletBalance)
  }
  const payTopup = async (existing?: WalletTopup) => {
    if (busy.current || !gatewayEnabled) return
    const value = existing?.amount ?? Number(amount)
    if (!Number.isFinite(value) || value < 1 || value > 10000) { setError('Enter a top-up amount between ₹1 and ₹10,000.'); return }
    busy.current = true; revision.current++; setBusyId(existing?.id ?? -1); setError(null)
    let createdHere = false
    try {
      let next = existing ? await apiClient.getWalletTopup(existing.id) : await apiClient.rechargeWallet(value, walletTopupIntent(value))
      createdHere = !existing
      if (!alive.current) return
      rememberTopup(next)
      if (next.state !== 'captured' && next.checkout) {
        next = await completeWalletTopup(next)
        if (!alive.current) return
        rememberTopup(next)
      }
      if (next.state === 'captured') {
        // Only clear the key known to have created this intent; another device may have created a listed top-up.
        if (createdHere) clearWalletTopupIntent(value)
        showToast('Wallet top-up confirmed.')
      } else showToast('Payment is pending. Refresh or resume this top-up; your balance changes after confirmation.')
    } catch (cause) {
      if (alive.current) {
        if (cause instanceof CheckoutDismissed) showToast(cause.message)
        else { setError((cause as Error).message); showToast('Check the top-up history before retrying. The same retry key will be reused.') }
      }
    } finally {
      busy.current = false
      if (alive.current) { setBusyId(null); void reload.current(); void refreshRef.current() }
    }
  }
  return <Screen nav={false}>
    <TopBar title="Canteen wallet" onBack={() => go('profile')} />
    <div className="px-5">
      <div className="rounded-3xl bg-ink p-6 text-white"><p className="text-sm text-white/70">Available balance</p><p className="mt-2 font-mono text-4xl font-bold">{rupee(walletBalance ?? user?.walletBalance ?? 0)}</p></div>
      <div className="mt-4 rounded-3xl bg-card p-5 shadow-sm">
        <h3 className="font-display text-sm font-bold">Add funds</h3>
        <p className="mt-1 text-xs text-ink-soft">{gatewayEnabled ? 'Secure payment through Razorpay. Funds appear after confirmation.' : 'Online wallet top-ups are unavailable until payments are configured.'}</p>
        <label className="mt-4 block text-xs font-semibold text-ink-soft">Amount (₹)<input type="number" min="1" max="10000" step="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} disabled={busyId !== null} className="mt-1 w-full rounded-2xl border border-line bg-paper px-4 py-3 font-mono text-base font-bold outline-none focus:border-tangerine" /></label>
        <div className="mt-3"><Button full disabled={!gatewayEnabled || busyId !== null || loading} onClick={() => { void payTopup() }}>{busyId === -1 ? 'Opening secure payment…' : 'Add funds securely'}</Button></div>
      </div>
      {error && <p role="alert" className="mt-4 rounded-2xl bg-berry-soft p-3 text-sm text-berry">{error}</p>}
      {loading && <p role="status" className="mt-4 text-sm text-ink-soft">Loading wallet…</p>}
      <div className="mt-6 mb-3 flex items-center justify-between"><h3 className="font-display font-bold">Top-up history</h3><button disabled={busyId !== null} onClick={() => { void reload.current() }} className="text-xs font-bold text-tangerine">Refresh</button></div>
      {!loading && !topups.length && <p className="text-sm text-ink-soft">No top-ups yet.</p>}
      {topups.map(topup => <div key={topup.id} className="mb-3 rounded-2xl bg-card p-4 shadow-sm">
        <div className="flex justify-between gap-4"><p className="text-sm font-bold">Wallet top-up #{topup.id}</p><span className="font-mono text-sm font-bold">{rupee(topup.amount)}</span></div>
        <p className="mt-2 text-xs text-ink-soft">{new Date(topup.createdAt).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} · {topup.state.replace(/_/g, ' ')}</p>
        {topup.state === 'captured' ? <p className="mt-2 text-xs font-bold text-mint">✓ Funds credited</p> : topup.checkout ? <div className="mt-3"><Button size="sm" full variant="soft" disabled={!gatewayEnabled || busyId !== null} onClick={() => { void payTopup(topup) }}>{busyId === topup.id ? 'Checking payment…' : 'Resume payment'}</Button></div> : <p className={'mt-2 text-xs ' + (topup.state === 'refund_required' ? 'text-berry' : 'text-ink-soft')}>{topup.state === 'refunded' ? 'Payment refunded. Your current balance is shown above.' : topup.state === 'refund_required' ? 'Payment could not be credited. Canteen staff must review its refund.' : topup.state === 'failed' ? 'Payment failed. Refresh to check whether it can be resumed.' : 'Awaiting confirmation. Refresh to check its status.'}</p>}
      </div>)}
      <h3 className="mt-6 mb-3 font-display font-bold">Transactions</h3>
      {!loading && !transactions.length && <p className="text-sm text-ink-soft">No transactions yet.</p>}
      {transactions.map(tx => <div key={tx.id} className="mb-3 rounded-2xl bg-card p-4 shadow-sm"><div className="flex justify-between gap-4"><p className="text-sm font-bold">{tx.description}</p><span className="font-mono text-sm font-bold">{rupee(tx.amount)}</span></div><p className="mt-2 text-xs text-ink-soft">{tx.dateFormatted ?? tx.createdAt} · {tx.status}</p></div>)}
    </div>
  </Screen>
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('login')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [checking, setChecking] = useState(apiClient.hasSession())
  const [menu, setMenu] = useState<MenuItem[]>([])
  const [orders, setOrders] = useState<StudentOrder[]>([])
  const [order, setOrder] = useState<StudentOrder | null>(null)
  const [notifications, setNotifications] = useState<StudentNotification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [menuLoading, setMenuLoading] = useState(false)
  const [menuError, setMenuError] = useState<string | null>(null)
  const [menuCategory, setMenuCategory] = useState<Category>('All')
  const [cart, setCart] = useState<CartLine[]>([])
  const [selected, setSelected] = useState<MenuItem | null>(null)
  const [banner, setBanner] = useState<SystemBanner | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionVersion = useRef(0)
  const refreshInFlight = useRef<symbol | null>(null)
  const menuLoaded = useRef(false)
  const orderSubmitLock = useRef(false)
  const userRef = useRef(user)
  userRef.current = user
  const showToast = (msg: string) => { if(toastTimer.current) clearTimeout(toastTimer.current); setToast(msg); toastTimer.current = setTimeout(() => setToast(null), 3500) }
  const clearSession = () => { sessionVersion.current++; refreshInFlight.current = null; menuLoaded.current = false; setUser(null); setMenu([]); setOrders([]); setOrder(null); setNotifications([]); setCart([]); setSelected(null); setError(null); setMenuError(null); setMenuLoading(false); setMenuCategory('All'); setBanner(null); setScreen('login'); setChecking(false); setLoading(false) }
  useEffect(() => {
    const expire = () => { const wasSignedIn = Boolean(userRef.current); clearSession(); if (wasSignedIn) showToast('Your session expired. Please sign in again.') }
    window.addEventListener(STUDENT_SESSION_EXPIRED, expire)
    let active = true
    const version = sessionVersion.current
    if (apiClient.hasSession()) apiClient.getMe().then(res => { if(active && version === sessionVersion.current && res.success && res.user) { setUser(res.user); setScreen('home') } }).catch(e => { if(active && version === sessionVersion.current) setError((e as Error).message) }).finally(() => { if(active && version === sessionVersion.current) setChecking(false) })
    return () => { active = false; window.removeEventListener(STUDENT_SESSION_EXPIRED, expire); if(toastTimer.current) clearTimeout(toastTimer.current) }
  }, [])
  const refresh = async () => {
    if (!user || refreshInFlight.current) return
    const version = sessionVersion.current
    const request = Symbol('student-refresh')
    refreshInFlight.current = request
    const current = () => version === sessionVersion.current && refreshInFlight.current === request
    setLoading(true)
    // Menu loading belongs to the menu request. Background polls keep existing food visible.
    setMenuLoading(!menuLoaded.current)
    const menuRequest = Promise.resolve().then(() => apiClient.getMenu()).then(items => {
      if (!Array.isArray(items)) throw new Error('The canteen returned an invalid menu. Please retry.')
      if (!current()) return
      menuLoaded.current = true
      setMenu(items)
      setMenuError(null)
      setCart(prev => prev.flatMap(line => { const next = items.find(item => item.id === line.item.id); return next ? [{ ...line, item: next }] : [] }))
      setSelected(prev => prev ? items.find(item => item.id === prev.id) ?? { ...prev, available: false } : null)
    }).catch(cause => {
      if (current()) setMenuError(cause instanceof Error ? cause.message : 'Cannot load the menu. Please retry.')
      throw cause
    }).finally(() => { if (current()) setMenuLoading(false) })
    try {
      const results = await Promise.allSettled([menuRequest,
        Promise.resolve().then(() => apiClient.getOrders()),
        Promise.resolve().then(() => apiClient.getNotifications()),
        Promise.resolve().then(() => apiClient.getMe())])
      if (!current()) return
      const [, ordersResult, notificationsResult, userResult] = results
      if (ordersResult.status === 'fulfilled') { setOrders(ordersResult.value); setOrder(prev => prev ? ordersResult.value.find(next => next.orderId === prev.orderId) ?? prev : null) }
      if (notificationsResult.status === 'fulfilled') setNotifications(notificationsResult.value)
      if (userResult.status === 'fulfilled' && userResult.value.user) setUser(userResult.value.user)
      const failure = results.find(result => result.status === 'rejected')
      setError(failure?.status === 'rejected' ? (failure.reason as Error).message : null)
      setBanner(failure ? 'network' : null)
    } finally {
      // An older session cannot unlock or clear the loading state of a newer request.
      if (refreshInFlight.current === request) {
        refreshInFlight.current = null
        if (version === sessionVersion.current) { setLoading(false); setMenuLoading(false) }
      }
    }
  }
  useEffect(() => { if(!user) return; void refresh(); const timer = setInterval(() => { if (document.visibilityState === 'visible') void refresh() }, 15000); return () => clearInterval(timer) }, [user?.id])
  const loginUser = async (roll: string, passcode: string) => { const res = await apiClient.login(roll, passcode); if(res.success && res.user) { sessionVersion.current++; setUser(res.user); setScreen('home'); setError(null); showToast(`Welcome, ${res.user.name}!`) }; return res }
  const registerUser = async (input: RegisterInput) => { const res = await apiClient.register(input); if(res.success && res.user) { sessionVersion.current++; setUser(res.user); setScreen('home'); setError(null); showToast(`Welcome, ${res.user.name}!`) }; return res }
  const logoutUser = async () => { clearSession(); const version = sessionVersion.current; await apiClient.logout(); if(version === sessionVersion.current) showToast('Logged out successfully') }
  const rememberOrder = (next: StudentOrder) => { setOrder(next); setOrders(prev => [next, ...prev.filter(row => row.orderId !== next.orderId)]) }
  const completePayment = async (pending: StudentOrder) => {
    const version = sessionVersion.current
    try {
      const next = await completeGatewayPayment(pending)
      if (version !== sessionVersion.current) throw new Error('Your session changed. Sign in to check Your Orders.')
      rememberOrder(next)
      if (next.payment === 'Paid') { clearCheckoutIntent(); setCart([]) }
      void refresh()
      return next
    } catch (cause) {
      if (cause instanceof CheckoutDismissed && version === sessionVersion.current) { showToast(cause.message); return pending }
      throw cause
    }
  }
  const submitOrder = async (paymentMethod: string) => {
    if (orderSubmitLock.current) throw new Error('An order is already being submitted.')
    if (!user || !cart.length) throw new Error('Sign in and add food before ordering.')
    if (cart.some(line => !line.item.available)) throw new Error('An item in your cart is currently unavailable. Remove it before ordering.')
    const version = sessionVersion.current
    const items = cart.map(line => ({ id: line.item.id, qty: line.qty }))
    const method = paymentMethod === 'wallet' ? 'wallet' : 'razorpay'
    const key = checkoutIntent(items, method)
    orderSubmitLock.current = true
    try {
      const next = await apiClient.createOrder(items, method, key)
      if (version !== sessionVersion.current) throw new Error('Your session changed. Sign in to check Your Orders.')
      rememberOrder(next)
      if (next.payment === 'Paid') { clearCheckoutIntent(); setCart([]); void refresh(); return next }
      if (next.checkout && next.status === 'Payment Pending') return await completePayment(next)
      return next
    } finally { orderSubmitLock.current = false }
  }
  const pickup = async () => { if(!order) return; const version = sessionVersion.current; const next = await apiClient.pickupOrder(order.orderId); if(version !== sessionVersion.current) throw new Error('Your session changed. Sign in to check Your Orders.'); setOrder(next); await refresh() }
  const markRead = async () => { const version = sessionVersion.current; await apiClient.markAllNotificationsRead(); if(version === sessionVersion.current) setNotifications(prev => prev.map(n => ({...n,unread:false}))) }
  const store: Store = {
    screen, user, menu, orders, order, notifications, loading, error, menuLoading, menuError, menuCategory, setMenuCategory, refresh, selectOrder: setOrder, submitOrder, completePayment, pickup, markRead,
    go: next => { if(!user && next !== 'login') { setScreen('login'); return }; setScreen(next) }, loginUser, registerUser, logoutUser,
    cart, add: (item, qty = 1) => { const current = menu.find(next => next.id === item.id); if(!current?.available) { showToast('This item is currently unavailable'); return }; setCart(prev => { const old = prev.find(l => l.item.id === current.id); return old ? prev.map(l => l.item.id === current.id ? {...l,qty:l.qty+qty} : l) : [...prev,{item:current,qty}] }); showToast(`${current.name} added`) },
    setQty: (id,qty) => setCart(prev => qty <= 0 ? prev.filter(l => l.item.id !== id) : prev.map(l => l.item.id === id ? {...l,qty} : l)), clear: () => setCart([]),
    cartCount: cart.reduce((sum,l) => sum+l.qty,0), cartTotal: cart.reduce((sum,l) => sum+l.qty*l.item.price,0), selected, select: setSelected, banner, setBanner, toast, showToast,
  }
  const screens: Record<Screen, ReactNode> = { login:<LoginScreen />, home:<HomeScreen />, menu:<MenuScreen />, details:<DetailsScreen />, cart:<CartScreen />, checkout:<CheckoutScreen />, confirm:<ConfirmScreen />, tracking:<TrackingScreen />, ready:<ReadyScreen />, history:<HistoryScreen />, orderDetails:<OrderDetailsScreen />, notifications:<NotificationsScreen />, profile:<ProfileScreen />, wallet:<WalletScreen /> }
  return <Ctx.Provider value={store}><main className="student-shell relative mx-auto h-dvh min-h-0 w-full overflow-hidden bg-paper">{checking ? <div className="grid h-full place-items-center text-sm text-ink-soft">Checking your student session…</div> : screens[user ? screen : 'login']}<ToastBanner /></main></Ctx.Provider>
}
