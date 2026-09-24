import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { apiClient } from './lib/apiClient'
import type { UserProfile, AuthResponse, RegisterInput } from './server/auth'
import AdminDashboard from './components/AdminDashboard'

/* ============================================================================
   Smart Canteen OS — Student Mobile App
   A connected first-draft prototype. 13 screens + order/system states,
   rendered inside a 390 × 844 device frame.
   ========================================================================== */

/* ------------------------------- Data model ------------------------------- */

type Category = 'All' | 'Snacks' | 'Meals' | 'Beverages'

type MenuItem = {
  id: string
  name: string
  desc: string
  price: number
  rating: number
  prepMins: number
  category: Exclude<Category, 'All'>
  veg: boolean
  available: boolean
  tag?: string
  emoji: string
  photo: string
}

type OrderStatus =
  | 'Queued'
  | 'Preparing'
  | 'Ready'
  | 'Completed'
  | 'Delayed'
  | 'Cancelled'

type PastOrder = {
  id: string
  number: string
  date: string
  items: { name: string; qty: number }[]
  total: number
  status: OrderStatus
  payment: 'Paid' | 'Failed' | 'Refunded'
}

const img = (id: string) =>
  `https://images.unsplash.com/photo-${id}?w=360&h=360&fit=crop&auto=format`

const MENU: MenuItem[] = [
  {
    id: 'veg-burger',
    name: 'Veg Burger',
    desc: 'Crispy patty, lettuce, house sauce in a toasted bun.',
    price: 60,
    rating: 4.6,
    prepMins: 8,
    category: 'Snacks',
    veg: true,
    available: true,
    tag: 'Bestseller',
    emoji: '🍔',
    photo: img('1568901346375-23c9450c58cd'),
  },
  {
    id: 'paneer-wrap',
    name: 'Paneer Wrap',
    desc: 'Spiced paneer, onions & mint chutney rolled fresh.',
    price: 80,
    rating: 4.7,
    prepMins: 10,
    category: 'Meals',
    veg: true,
    available: true,
    tag: 'Chef’s pick',
    emoji: '🌯',
    photo: img('1626700051175-6818013e1d4f'),
  },
  {
    id: 'masala-maggi',
    name: 'Masala Maggi',
    desc: 'Classic hostel-night noodles with extra masala.',
    price: 40,
    rating: 4.8,
    prepMins: 7,
    category: 'Meals',
    veg: true,
    available: true,
    tag: 'Student fav',
    emoji: '🍜',
    photo: img('1612929633738-8fe44f7ec841'),
  },
  {
    id: 'cold-coffee',
    name: 'Cold Coffee',
    desc: 'Thick, frothy & chilled. The 4 PM lifesaver.',
    price: 50,
    rating: 4.5,
    prepMins: 5,
    category: 'Beverages',
    veg: true,
    available: true,
    emoji: '🥤',
    photo: img('1461023058943-07fcbe16d735'),
  },
  {
    id: 'tea',
    name: 'Masala Tea',
    desc: 'Freshly brewed cutting chai, served hot.',
    price: 15,
    rating: 4.4,
    prepMins: 4,
    category: 'Beverages',
    veg: true,
    available: true,
    emoji: '☕',
    photo: img('1571934811356-5cc061b6821f'),
  },
  {
    id: 'french-fries',
    name: 'French Fries',
    desc: 'Golden, salted & crunchy with peri-peri dip.',
    price: 55,
    rating: 4.5,
    prepMins: 6,
    category: 'Snacks',
    veg: true,
    available: true,
    emoji: '🍟',
    photo: img('1573080496219-bb080dd4f877'),
  },
  {
    id: 'veg-pizza',
    name: 'Veg Pizza',
    desc: 'Cheese-loaded personal pizza with garden veggies.',
    price: 120,
    rating: 4.6,
    prepMins: 14,
    category: 'Meals',
    veg: true,
    available: false,
    emoji: '🍕',
    photo: img('1513104890138-7c749659a591'),
  },
  {
    id: 'cheese-sandwich',
    name: 'Cheese Sandwich',
    desc: 'Grilled triple-cheese sandwich, gooey inside.',
    price: 70,
    rating: 4.3,
    prepMins: 8,
    category: 'Snacks',
    veg: true,
    available: true,
    emoji: '🥪',
    photo: img('1528735602780-2552fd46c7af'),
  },
]

const HISTORY: PastOrder[] = [
  {
    id: 'h1',
    number: '#1042',
    date: 'Today · 12:32 PM',
    items: [
      { name: 'Veg Burger', qty: 1 },
      { name: 'Cold Coffee', qty: 1 },
      { name: 'French Fries', qty: 1 },
    ],
    total: 165,
    status: 'Preparing',
    payment: 'Paid',
  },
  {
    id: 'h2',
    number: '#1031',
    date: 'Yesterday · 5:10 PM',
    items: [
      { name: 'Masala Maggi', qty: 2 },
      { name: 'Masala Tea', qty: 2 },
    ],
    total: 110,
    status: 'Completed',
    payment: 'Paid',
  },
  {
    id: 'h3',
    number: '#1018',
    date: '28 Jul · 1:45 PM',
    items: [{ name: 'Paneer Wrap', qty: 1 }],
    total: 80,
    status: 'Completed',
    payment: 'Paid',
  },
  {
    id: 'h4',
    number: '#0994',
    date: '26 Jul · 4:20 PM',
    items: [{ name: 'Cheese Sandwich', qty: 1 }],
    total: 70,
    status: 'Cancelled',
    payment: 'Refunded',
  },
]

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
  | 'states'

type CartLine = { item: MenuItem; qty: number }

type Store = {
  go: (s: Screen) => void
  screen: Screen
  user: UserProfile | null
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

const DEPTH: Record<Screen, number> = {
  login: 0, home: 1, menu: 2, details: 3, cart: 2,
  checkout: 3, confirm: 4, tracking: 2, ready: 3,
  history: 2, orderDetails: 3, notifications: 2, profile: 2, states: 3,
}

type SystemBanner = 'offline' | 'reconnecting' | 'network'

const Ctx = createContext<Store>(null as unknown as Store)
const useStore = () => useContext(Ctx)

/* ------------------------------ Primitives -------------------------------- */

const rupee = (n: number) => `₹${n}`

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
    Queued: { c: 'bg-slate-soft text-slate', dot: 'bg-slate' },
    Preparing: { c: 'bg-tangerine-soft text-tangerine-dark', dot: 'bg-tangerine' },
    Ready: { c: 'bg-mint-soft text-mint', dot: 'bg-mint' },
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

function StatusBar({ dark = false }: { dark?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between px-6 pt-3 pb-1 text-[13px] font-semibold ${dark ? 'text-white' : 'text-ink'}`}
    >
      <span className="font-mono">12:41</span>
      <div className="flex items-center gap-1.5">
        <Icon name="wifi" className="h-3.5 w-3.5" />
        <span className="text-[11px]">5G</span>
        <span
          className={`ml-1 inline-block h-3 w-6 rounded-sm border ${dark ? 'border-white/60' : 'border-ink/50'} relative`}
        >
          <span
            className={`absolute inset-[2px] right-1.5 rounded-[1px] ${dark ? 'bg-white' : 'bg-ink'}`}
          />
        </span>
      </div>
    </div>
  )
}

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
    <div className="relative flex h-full flex-col bg-paper">
      <StatusBar />
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
  const { banner, setBanner } = useStore()
  if (!banner) return null
  const cfg = {
    offline: { c: 'bg-ink text-white', t: 'You’re offline', s: 'Showing your last synced menu.', i: 'off' },
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
        <button onClick={() => setBanner('reconnecting')} className="rounded-lg bg-white/20 px-3 py-1 text-xs font-bold">
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
  const { loginUser, registerUser, showToast } = useStore()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [prefix, setPrefix] = useState('21CS')
  const [rollNumber, setRollNumber] = useState('1042')
  const [passcode, setPasscode] = useState('000000')
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
  const [forgotRoll, setForgotRoll] = useState('21CS1042')
  const [forgotStep, setForgotStep] = useState<'request' | 'reset'>('request')
  const [generatedOtp, setGeneratedOtp] = useState<string | null>(null)
  const [enteredOtp, setEnteredOtp] = useState('')
  const [newPasscode, setNewPasscode] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotError, setForgotError] = useState<string | null>(null)

  const demoAccounts = [
    { label: 'Aarav', prefix: '21CS', roll: '1042', dept: 'CSE', emoji: '👨‍💻' },
    { label: 'Priya', prefix: '21IT', roll: '2015', dept: 'IT', emoji: '👩‍💻' },
    { label: 'Rohan', prefix: '22EC', roll: '3088', dept: 'ECE', emoji: '⚡' },
  ]

  const handleQuickSelect = (d: { prefix: string; roll: string }) => {
    setPrefix(d.prefix)
    setRollNumber(d.roll)
    setPasscode('000000')
    setErrorMessage(null)
  }

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
        setGeneratedOtp(res.otp || '482910')
        setEnteredOtp(res.otp || '482910')
        setForgotStep('reset')
        showToast('OTP code sent to your registered contact!')
      } else {
        setForgotError(res.message)
      }
    } catch {
      setForgotError('Error requesting reset code.')
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
      if (res.success && res.user) {
        showToast(res.message || 'Passcode updated! Logging in...')
        setShowForgotModal(false)
        await loginUser(forgotRoll.trim(), newPasscode)
      } else {
        setForgotError(res.message)
      }
    } catch {
      setForgotError('Error resetting passcode.')
    } finally {
      setForgotLoading(false)
    }
  }

  return (
    <div className="relative flex h-full flex-col overflow-y-auto bg-ink text-white">
      <StatusBar dark />
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
            <span className="text-base">🍔</span> Campus Canteen · Live
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

          {errorMessage && (
            <div className="mb-3.5 flex items-start gap-2 rounded-2xl bg-berry-soft p-3 text-xs text-berry">
              <span className="text-sm shrink-0">⚠️</span>
              <p className="leading-snug">{errorMessage}</p>
            </div>
          )}

          {mode === 'login' ? (
            <form onSubmit={handleLoginSubmit}>
              {/* Demo quick pills */}
              <div className="mb-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-ink-soft">
                    Quick demo accounts
                  </span>
                  <span className="text-[10px] text-tangerine font-semibold">
                    1-tap fill
                  </span>
                </div>
                <div className="mt-1.5 flex gap-1.5 overflow-x-auto pb-1">
                  {demoAccounts.map((d) => {
                    const isSelected = prefix === d.prefix && rollNumber === d.roll
                    return (
                      <button
                        key={d.label}
                        type="button"
                        onClick={() => handleQuickSelect(d)}
                        className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-semibold transition-all ${
                          isSelected
                            ? 'border-tangerine bg-tangerine-soft text-tangerine-dark font-bold'
                            : 'border-line bg-paper text-ink-soft hover:border-black/20'
                        }`}
                      >
                        <span>{d.emoji}</span>
                        <span>{d.label}</span>
                        <span className="font-mono text-[10px] opacity-70">
                          {d.prefix}{d.roll}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Roll number inputs */}
              <label className="block text-xs font-semibold text-ink-soft">
                College Roll ID
              </label>
              <div className="mt-1 flex items-center gap-2 rounded-2xl border border-line bg-paper px-3 py-2.5">
                <select
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  className="bg-transparent font-mono text-sm font-bold text-ink outline-none cursor-pointer"
                >
                  <option value="21CS">21CS</option>
                  <option value="21IT">21IT</option>
                  <option value="22EC">22EC</option>
                  <option value="23ME">23ME</option>
                  <option value="23EE">23EE</option>
                </select>
                <span className="text-line">|</span>
                <input
                  type="text"
                  value={rollNumber}
                  onChange={(e) => setRollNumber(e.target.value)}
                  placeholder="1042"
                  className="w-full bg-transparent font-mono text-sm font-semibold text-ink outline-none placeholder:text-ink-soft/50"
                />
              </div>

              {/* Passcode input */}
              <div className="mt-3 flex items-center justify-between">
                <label className="text-xs font-semibold text-ink-soft">
                  6-Digit Passcode
                </label>
                <span className="text-[10px] text-ink-soft">Default: 000000</span>
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
                    'Register & Claim ₹250 🎁'
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
                  Enter your registered college roll number to receive a one-time OTP code.
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
                {generatedOtp && (
                  <div className="rounded-2xl border border-amber/30 bg-amber-soft p-3 text-xs">
                    <p className="font-bold text-ink">📩 Simulated SMS Notification:</p>
                    <p className="mt-0.5 text-ink-soft">
                      Your Canteen OS security code is{' '}
                      <span className="font-mono font-extrabold text-tangerine text-sm">{generatedOtp}</span>
                    </p>
                  </div>
                )}
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
  const cats: Category[] = ['All', 'Snacks', 'Meals', 'Beverages']
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

function SearchBar({ placeholder = 'Search burgers, wraps, chai…' }) {
  return (
    <div className="mx-5 flex items-center gap-3 rounded-2xl bg-card px-4 py-3 shadow-sm">
      <Icon name="search" className="h-5 w-5 text-ink-soft" />
      <input
        placeholder={placeholder}
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
        <img
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
  const { go, select, user } = useStore()
  const firstName = user?.name ? user.name.split(' ')[0] : 'Aarav'
  const popular = MENU.filter((m) => m.tag).slice(0, 4)
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
            Main Block Canteen · Open till 8 PM
          </div>
        </div>
        <button
          onClick={() => go('notifications')}
          className="relative grid h-11 w-11 place-items-center rounded-full bg-card shadow-sm"
        >
          <Icon name="bell" className="h-5 w-5" />
          <span className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-tangerine ring-2 ring-card" />
        </button>
      </div>

      <div className="mt-3">
        <SearchBar />
      </div>

      {/* Live order strip */}
      <button
        onClick={() => go('tracking')}
        className="mx-5 mt-4 flex w-[calc(100%-2.5rem)] items-center gap-3 overflow-hidden rounded-3xl bg-ink p-4 text-left text-white"
      >
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-tangerine text-xl">
          🍔
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold">#1042</span>
            <StatusBadge status="Preparing" />
          </div>
          <p className="mt-0.5 text-xs text-white/70">
            Queue position 4 · ready in ~5 min
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-bold text-amber">04:32</p>
          <p className="text-[10px] text-white/60">Track →</p>
        </div>
      </button>

      {/* Categories quick */}
      <div className="mt-5 grid grid-cols-4 gap-2 px-5">
        {[
          { e: '🍟', l: 'Snacks' },
          { e: '🍜', l: 'Meals' },
          { e: '🥤', l: 'Drinks' },
          { e: '🔥', l: 'Trending' },
        ].map((c) => (
          <button
            key={c.l}
            onClick={() => go('menu')}
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
  const [cat, setCat] = useState<Category>('All')
  const [query, setQuery] = useState('')
  const list = MENU.filter(
    (m) =>
      (cat === 'All' || m.category === cat) &&
      (query === '' || m.name.toLowerCase().includes(query.toLowerCase()))
  )
  return (
    <Screen>
      <TopBar title="Canteen Menu" subtitle={`${MENU.filter(m => m.available).length} items available · live`} />
      <div className="mx-5 flex items-center gap-3 rounded-2xl bg-card px-4 py-3 shadow-sm">
        <Icon name="search" className="h-5 w-5 text-ink-soft" />
        <input
          placeholder="Search burgers, wraps, chai…"
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
        {list.length === 0 ? (
          <EmptyState
            emoji="🔍"
            title="No items found"
            body={`Nothing matches "${query}". Try a different search.`}
            cta="Clear search"
            onCta={() => setQuery('')}
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
  const item = selected ?? MENU[0]
  const line = cart.find((l) => l.item.id === item.id)
  const [qty, setLocalQty] = useState(line?.qty ?? 1)
  return (
    <Screen nav={false}>
      <div className="relative">
        <div className="relative h-64 w-full overflow-hidden bg-paper">
          <img
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
            🔥 {320 + item.prepMins * 12} kcal
          </div>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-ink-soft">{item.desc}</p>

        {item.available ? (
          <>
            <h3 className="mt-6 font-display text-sm font-bold">
              Make it yours
            </h3>
            <div className="mt-2 flex flex-col gap-2">
              {[
                { l: 'Extra cheese', p: 15 },
                { l: 'Spicy peri-peri', p: 0 },
                { l: 'No onions', p: 0 },
              ].map((o, i) => (
                <label
                  key={o.l}
                  className="flex items-center justify-between rounded-2xl bg-card px-4 py-3 shadow-sm"
                >
                  <span className="text-sm font-semibold">{o.l}</span>
                  <span className="flex items-center gap-2 text-xs text-ink-soft">
                    {o.p ? `+${rupee(o.p)}` : 'Free'}
                    <input
                      type="checkbox"
                      defaultChecked={i === 1}
                      className="h-4 w-4 accent-tangerine"
                    />
                  </span>
                </label>
              ))}
            </div>
          </>
        ) : (
          <div className="mt-6 rounded-2xl border border-berry-soft bg-berry-soft p-4 text-center">
            <p className="font-display font-bold text-berry">
              Currently unavailable
            </p>
            <p className="mt-1 text-xs text-berry/80">
              This item is out of stock. Get notified when it’s back.
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
            Notify me & back to menu
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
        <img
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
  const packaging = cart.length ? 8 : 0
  const gst = Math.round(cartTotal * 0.05)
  const total = cartTotal + packaging + gst
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

          <div className="mx-5 mt-5 flex items-center gap-3 rounded-2xl border border-dashed border-tangerine bg-tangerine-soft px-4 py-3">
            <span className="text-lg">🏷️</span>
            <input
              placeholder="Add a coupon or campus code"
              className="w-full bg-transparent text-sm outline-none placeholder:text-tangerine-dark/60"
            />
            <button className="text-xs font-bold text-tangerine-dark">Apply</button>
          </div>

          <div className="mx-5 mt-4 rounded-3xl bg-card p-5 shadow-sm">
            <h3 className="font-display text-sm font-bold">Bill details</h3>
            <div className="mt-3 flex flex-col gap-2 text-sm">
              <Row l="Item total" v={rupee(cartTotal)} />
              <Row l="Packaging" v={rupee(packaging)} />
              <Row l="GST (5%)" v={rupee(gst)} />
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
  const { cart, cartTotal, go, clear, user } = useStore()
  const [pay, setPay] = useState('upi')
  const [failed, setFailed] = useState(false)
  const total = cartTotal + 8 + Math.round(cartTotal * 0.05)
  return (
    <Screen nav={false}>
      <TopBar title="Checkout" onBack={() => go('cart')} />
      <div className="px-5">
        {failed && (
          <div className="mb-4 flex items-start gap-3 rounded-2xl bg-berry-soft p-4 [animation:sco-rise_0.25s_ease]">
            <span className="text-xl">⚠️</span>
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-berry">
                Payment failed
              </p>
              <p className="mt-0.5 text-xs text-berry/80">
                Your bank declined the transaction. No money was deducted.
              </p>
            </div>
            <PaymentBadge status="Failed" />
          </div>
        )}

        {/* Pickup */}
        <h3 className="font-display text-sm font-bold">Pickup details</h3>
        <div className="mt-2 rounded-3xl bg-card p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <Icon name="pin" className="h-5 w-5 text-tangerine" />
            <div className="flex-1">
              <p className="text-sm font-bold">Main Block Canteen</p>
              <p className="text-xs text-ink-soft">Counter 2 · Self pickup</p>
            </div>
            <span className="rounded-full bg-mint-soft px-2.5 py-1 text-[11px] font-bold text-mint">
              Open
            </span>
          </div>
          <div className="mt-3 flex items-center gap-3 border-t border-line pt-3">
            <Icon name="clock" className="h-5 w-5 text-tangerine" />
            <div className="flex-1">
              <p className="text-sm font-bold">As soon as possible</p>
              <p className="text-xs text-ink-soft">
                Estimated ready by ~12:46 PM
              </p>
            </div>
          </div>
        </div>

        {/* Payment methods */}
        <h3 className="mt-6 font-display text-sm font-bold">Payment method</h3>
        <div className="mt-2 flex flex-col gap-2">
          {[
            { id: 'upi', l: 'Campus UPI', s: user?.upiId || 'aarav@campuspay', e: '🟣' },
            { id: 'wallet', l: 'Canteen Wallet', s: `Balance ₹${user?.walletBalance ?? 340}`, e: '👛' },
            { id: 'card', l: 'Card', s: '•••• 4291', e: '💳' },
          ].map((p) => (
            <button
              key={p.id}
              onClick={() => setPay(p.id)}
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
            <Row l="Taxes & packaging" v={rupee(8 + Math.round(cartTotal * 0.05))} />
            <div className="my-1 border-t border-dashed border-line" />
            <Row l="To pay" v={rupee(total)} bold />
          </div>
        </div>
      </div>

      <div className="sticky bottom-0 mt-6 flex flex-col gap-2 border-t border-line bg-paper/95 px-5 py-4 backdrop-blur">
        <Button
          full
          onClick={() => {
            clear()
            go('confirm')
          }}
        >
          Pay {rupee(total)} & place order
        </Button>
        <button
          onClick={() => setFailed((v) => !v)}
          className="text-center text-[11px] font-semibold text-ink-soft"
        >
          {failed ? 'Reset payment state' : 'Preview payment-failed state'}
        </button>
      </div>
    </Screen>
  )
}

function ConfirmScreen() {
  const { go } = useStore()
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-paper">
      <StatusBar />
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
          Your food is now in the queue. Track your position and countdown live.
        </p>

        <div className="mt-7 w-full rounded-3xl border border-line bg-card p-6 shadow-sm">
          <p className="text-xs font-semibold text-ink-soft">Your order number</p>
          <p className="mt-1 font-mono text-4xl font-bold tracking-tight text-tangerine">
            #1042
          </p>
          <div className="mt-4 flex items-center justify-center gap-6 border-t border-dashed border-line pt-4">
            <div>
              <p className="font-mono text-lg font-bold">4</p>
              <p className="text-[11px] text-ink-soft">Queue pos.</p>
            </div>
            <div className="h-8 w-px bg-line" />
            <div>
              <p className="font-mono text-lg font-bold text-tangerine">~5 min</p>
              <p className="text-[11px] text-ink-soft">Ready in</p>
            </div>
            <div className="h-8 w-px bg-line" />
            <div>
              <p className="font-mono text-lg font-bold">12:46</p>
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

const TIMELINE: { key: string; label: string; note: string }[] = [
  { key: 'placed', label: 'Placed', note: 'Order received' },
  { key: 'queued', label: 'Queued', note: 'You’re in line' },
  { key: 'preparing', label: 'Preparing', note: 'Chef is cooking' },
  { key: 'ready', label: 'Ready', note: 'Pick up at counter' },
  { key: 'picked', label: 'Picked Up', note: 'Collected' },
  { key: 'completed', label: 'Completed', note: 'Enjoy!' },
]

function useCountdown(start: number) {
  const [secs, setSecs] = useState(start)
  const ref = useRef(start)
  useEffect(() => {
    const t = setInterval(() => {
      ref.current = ref.current > 0 ? ref.current - 1 : 0
      setSecs(ref.current)
    }, 1000)
    return () => clearInterval(t)
  }, [])
  const mm = String(Math.floor(secs / 60)).padStart(2, '0')
  const ss = String(secs % 60).padStart(2, '0')
  return { mm, ss, secs }
}

function TrackingScreen() {
  const { go } = useStore()
  const { mm, ss, secs } = useCountdown(272) // 04:32
  const activeIdx = 2 // Preparing
  const progress = Math.min(100, Math.max(6, ((300 - secs) / 300) * 100))

  return (
    <Screen>
      <TopBar
        title="Live Order Tracking"
        onBack={() => go('home')}
        right={<StatusBadge status="Preparing" />}
      />

      {/* Order + countdown hero */}
      <div className="mx-5 overflow-hidden rounded-3xl bg-ink p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-white/60">Order number</p>
            <p className="font-mono text-2xl font-bold">#1042</p>
          </div>
          <div className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold">
            <span className="h-2 w-2 rounded-full bg-mint [animation:sco-pulse_1.2s_ease-in-out_infinite]" />
            Live
          </div>
        </div>

        <div className="mt-6 text-center">
          <p className="text-xs uppercase tracking-widest text-white/50">
            Ready in about
          </p>
          <p className="mt-1 font-mono text-6xl font-bold tracking-tight text-amber tabular-nums">
            {mm}:{ss}
          </p>
          <p className="mt-1 text-xs text-white/60">
            Expected ready time · 12:46 PM
          </p>
        </div>

        {/* progress rail */}
        <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-white/15">
          <div
            className="h-full rounded-full bg-gradient-to-r from-amber to-tangerine transition-all duration-1000"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Queue + orders-ahead cards */}
      <div className="mt-4 grid grid-cols-2 gap-3 px-5">
        <div className="rounded-3xl bg-card p-4 shadow-sm">
          <p className="text-xs font-semibold text-ink-soft">Queue position</p>
          <p className="mt-1 font-mono text-3xl font-bold text-tangerine">
            #4
          </p>
          <div className="mt-2 flex gap-1">
            {[1, 2, 3, 4].map((n) => (
              <span
                key={n}
                className={`h-1.5 flex-1 rounded-full ${n === 4 ? 'bg-tangerine' : 'bg-line'}`}
              />
            ))}
          </div>
        </div>
        <div className="rounded-3xl bg-card p-4 shadow-sm">
          <p className="text-xs font-semibold text-ink-soft">Orders ahead</p>
          <p className="mt-1 font-mono text-3xl font-bold">3</p>
          <p className="mt-2 text-[11px] text-ink-soft">
            Moving fast · ~90s each
          </p>
        </div>
      </div>

      {/* ETA card (rule-based now, ML-ready later) */}
      <div className="mx-5 mt-3 flex items-center gap-3 rounded-3xl bg-mint-soft p-4">
        <div className="grid h-11 w-11 place-items-center rounded-2xl bg-mint text-white">
          <Icon name="clock" className="h-6 w-6" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold text-mint">You’ll be served around 12:46 PM</p>
          <p className="text-[11px] text-mint/80">
            Smart estimate, updated as the queue moves.
          </p>
        </div>
      </div>

      {/* Timeline */}
      <div className="mx-5 mt-5 rounded-3xl bg-card p-5 shadow-sm">
        <h3 className="mb-4 font-display text-sm font-bold">Order timeline</h3>
        <div className="relative flex flex-col gap-0">
          {TIMELINE.map((step, i) => {
            const done = i < activeIdx
            const active = i === activeIdx
            const last = i === TIMELINE.length - 1
            return (
              <div key={step.key} className="relative flex gap-4 pb-5 last:pb-0">
                {!last && (
                  <span
                    className={`absolute left-[13px] top-7 h-full w-0.5 ${done ? 'bg-mint' : 'bg-line'}`}
                  />
                )}
                <div
                  className={`relative z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ${
                    done
                      ? 'bg-mint text-white'
                      : active
                        ? 'bg-tangerine text-white'
                        : 'bg-paper text-ink-soft'
                  }`}
                >
                  {done ? (
                    <Icon name="check" className="h-4 w-4" />
                  ) : active ? (
                    <span className="h-2.5 w-2.5 rounded-full bg-white [animation:sco-pulse_1.2s_ease-in-out_infinite]" />
                  ) : (
                    <span className="h-2 w-2 rounded-full bg-current opacity-40" />
                  )}
                </div>
                <div className="flex flex-1 items-center justify-between">
                  <div>
                    <p
                      className={`text-sm font-bold ${active ? 'text-tangerine' : done ? 'text-ink' : 'text-ink-soft'}`}
                    >
                      {step.label}
                    </p>
                    <p className="text-[11px] text-ink-soft">{step.note}</p>
                  </div>
                  {active && (
                    <span className="rounded-full bg-tangerine-soft px-2.5 py-1 text-[10px] font-bold text-tangerine-dark">
                      In progress
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mx-5 mt-4 flex gap-3">
        <Button variant="ghost" full onClick={() => go('ready')}>
          Simulate “Ready”
        </Button>
        <Button variant="dark" full onClick={() => go('notifications')}>
          Notifications
        </Button>
      </div>
    </Screen>
  )
}

function ReadyScreen() {
  const { go } = useStore()
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-mint text-white">
      <StatusBar dark />
      <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        <div className="relative">
          <span className="absolute inset-0 rounded-full bg-white/40 [animation:sco-ping_1.8s_ease-out_infinite]" />
          <div className="relative grid h-28 w-28 place-items-center rounded-full bg-white text-6xl">
            🔔
          </div>
        </div>
        <p className="mt-8 text-sm font-semibold uppercase tracking-widest text-white/80">
          Order #1042
        </p>
        <h1 className="mt-2 font-display text-4xl font-extrabold">
          Your food is ready!
        </h1>
        <p className="mt-3 max-w-xs text-sm text-white/85">
          Head to <b>Counter 2</b> at the Main Block Canteen and show this
          screen to collect your order.
        </p>

        <div className="mt-8 w-full rounded-3xl bg-white/15 p-5 backdrop-blur">
          <div className="flex items-center justify-center gap-8">
            <div>
              <p className="font-mono text-3xl font-bold">02</p>
              <p className="text-[11px] text-white/70">Counter</p>
            </div>
            <div className="h-10 w-px bg-white/30" />
            <div>
              <p className="font-mono text-3xl font-bold">1042</p>
              <p className="text-[11px] text-white/70">Show at pickup</p>
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2 px-6 pb-8">
        <button
          onClick={() => go('history')}
          className="w-full rounded-2xl bg-white py-3.5 font-semibold text-mint active:scale-[0.98]"
        >
          Mark as picked up
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
  const { go } = useStore()
  const live = order.status === 'Preparing' || order.status === 'Queued'
  return (
    <button
      onClick={() => go(live ? 'tracking' : 'orderDetails')}
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
        <span className="text-xs text-ink-soft">{order.date}</span>
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
  const [tab, setTab] = useState<'active' | 'past'>('active')
  const active = HISTORY.filter(
    (o) => o.status === 'Preparing' || o.status === 'Queued'
  )
  const past = HISTORY.filter(
    (o) => o.status !== 'Preparing' && o.status !== 'Queued'
  )
  const list = tab === 'active' ? active : past
  return (
    <Screen>
      <TopBar title="Your Orders" />
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
          onCta={() => window.scrollTo(0, 0)}
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
  const { go } = useStore()
  const o = HISTORY[1] // completed order
  return (
    <Screen nav={false}>
      <TopBar
        title={`Order ${o.number}`}
        subtitle={o.date}
        onBack={() => go('history')}
        right={<StatusBadge status={o.status} />}
      />
      <div className="px-5">
        <div className="rounded-3xl bg-card p-5 shadow-sm">
          <h3 className="font-display text-sm font-bold">Items</h3>
          <div className="mt-3 flex flex-col gap-3">
            {o.items.map((it) => {
              const m = MENU.find((x) => x.name === it.name)
              return (
                <div key={it.name} className="flex items-center gap-3">
                  <div className="h-12 w-12 overflow-hidden rounded-xl bg-paper">
                    {m && (
                      <img
                        src={m.photo}
                        alt={it.name}
                        className="h-full w-full object-cover"
                      />
                    )}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-bold">{it.name}</p>
                    <p className="text-xs text-ink-soft">Qty {it.qty}</p>
                  </div>
                  <span className="font-mono text-sm font-semibold">
                    {rupee((m?.price ?? 0) * it.qty)}
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
            <Row l="Item total" v={rupee(o.total)} />
            <Row l="Paid via" v="Campus UPI" />
            <div className="my-1 border-t border-dashed border-line" />
            <Row l="Total paid" v={rupee(o.total)} bold />
          </div>
        </div>

        <div className="mt-4 rounded-3xl bg-card p-5 shadow-sm">
          <h3 className="font-display text-sm font-bold">Pickup</h3>
          <div className="mt-3 flex items-center gap-3">
            <Icon name="pin" className="h-5 w-5 text-tangerine" />
            <div>
              <p className="text-sm font-bold">Main Block Canteen · Counter 2</p>
              <p className="text-xs text-ink-soft">Collected at 5:22 PM</p>
            </div>
          </div>
        </div>

        <div className="mt-5 flex gap-3">
          <Button variant="ghost" full onClick={() => go('menu')}>
            Reorder
          </Button>
          <Button variant="dark" full>
            Get invoice
          </Button>
        </div>
      </div>
    </Screen>
  )
}

function NotificationsScreen() {
  const { go } = useStore()
  const notes = [
    {
      e: '🔔',
      c: 'mint',
      t: 'Your order #1042 is ready!',
      s: 'Collect from Counter 2 now.',
      time: 'Just now',
      unread: true,
    },
    {
      e: '👨‍🍳',
      c: 'tangerine',
      t: 'Order #1042 is being prepared',
      s: 'You’re 4th in the queue · ready ~12:46 PM.',
      time: '3 min ago',
      unread: true,
    },
    {
      e: '✅',
      c: 'slate',
      t: 'Order #1042 placed',
      s: 'Payment of ₹165 successful via Campus UPI.',
      time: '8 min ago',
      unread: false,
    },
    {
      e: '🏷️',
      c: 'amber',
      t: 'Flat ₹20 off on cold beverages',
      s: 'Beat the heat — valid till 6 PM today.',
      time: '2 h ago',
      unread: false,
    },
    {
      e: '🍕',
      c: 'berry',
      t: 'Veg Pizza is back in stock',
      s: 'The item you wanted is available again.',
      time: 'Yesterday',
      unread: false,
    },
  ]
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
          <button className="text-xs font-bold text-tangerine">
            Mark all read
          </button>
        }
      />
      <div className="flex flex-col gap-2 px-5">
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
  const { go, setBanner, user, logoutUser } = useStore()
  const initial = user?.name ? user.name.charAt(0) : 'A'
  const fullName = user?.name || 'Aarav Sharma'
  const roll = user?.rollNumber || '21CS1042'
  const branch = user?.branch || 'B.Tech CSE'
  const walletBal = user?.walletBalance ?? 340
  const totalOrders = user?.totalOrders ?? 38
  const totalSpent = user?.totalSpent ? `₹${(user.totalSpent / 1000).toFixed(1)}k` : '₹4.2k'
  const savedMins = user?.savedMinutes ?? 12

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
            { n: `${savedMins}`, l: 'Saved min' },
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
            { i: '👛', l: 'Canteen wallet', s: () => {} },
            { i: '🎨', l: 'Design states gallery', s: () => go('states') },
            { i: '⚙️', l: 'Settings & preferences', s: () => {} },
            { i: '❓', l: 'Help & support', s: () => {} },
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

        <p className="mb-2 mt-5 text-xs font-semibold text-ink-soft">
          Preview connection states
        </p>
        <div className="grid grid-cols-3 gap-2">
          <Button size="sm" variant="soft" onClick={() => setBanner('offline')}>
            Offline
          </Button>
          <Button size="sm" variant="soft" onClick={() => setBanner('reconnecting')}>
            Reconnect
          </Button>
          <Button size="sm" variant="soft" onClick={() => setBanner('network')}>
            Net error
          </Button>
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

/* ---- Design states gallery (loading, empty, errors, etc.) ---- */

function StatesScreen() {
  const { go } = useStore()
  return (
    <Screen nav={false}>
      <TopBar title="Design states" onBack={() => go('profile')} subtitle="Loading · empty · error variants" />
      <div className="flex flex-col gap-5 px-5">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
            Loading (skeleton)
          </p>
          <div className="flex flex-col gap-3">
            {[0, 1].map((i) => (
              <div key={i} className="flex gap-3 rounded-3xl bg-card p-3 shadow-sm">
                <div className="sco-shimmer h-24 w-24 rounded-2xl" />
                <div className="flex-1 space-y-2 py-1">
                  <div className="sco-shimmer h-3 w-3/4 rounded-full" />
                  <div className="sco-shimmer h-3 w-full rounded-full" />
                  <div className="sco-shimmer h-3 w-1/2 rounded-full" />
                  <div className="sco-shimmer mt-3 h-6 w-20 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
            Loading spinner
          </p>
          <div className="grid place-items-center rounded-3xl bg-card p-8 shadow-sm">
            <span className="h-10 w-10 rounded-full border-4 border-line border-t-tangerine [animation:sco-spin_0.8s_linear_infinite]" />
            <p className="mt-3 text-xs text-ink-soft">Loading fresh menu…</p>
          </div>
        </div>

        {[
          {
            e: '🛒',
            t: 'Empty cart',
            b: 'Add items to get started.',
          },
          {
            e: '🧾',
            t: 'Empty order history',
            b: 'Your orders will show up here.',
          },
          {
            e: '🍕',
            t: 'Food unavailable',
            b: 'This item is out of stock right now.',
          },
        ].map((s) => (
          <div key={s.t}>
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
              {s.t}
            </p>
            <div className="flex items-center gap-4 rounded-3xl bg-card p-5 shadow-sm">
              <div className="grid h-16 w-16 place-items-center rounded-2xl bg-paper text-3xl">
                {s.e}
              </div>
              <div>
                <p className="font-display font-bold">{s.t}</p>
                <p className="text-xs text-ink-soft">{s.b}</p>
              </div>
            </div>
          </div>
        ))}

        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
            Payment failed
          </p>
          <div className="flex items-center gap-3 rounded-3xl bg-berry-soft p-4">
            <span className="text-2xl">⚠️</span>
            <div className="flex-1">
              <p className="font-display font-bold text-berry">Payment failed</p>
              <p className="text-xs text-berry/80">
                Bank declined · no money deducted.
              </p>
            </div>
            <PaymentBadge status="Failed" />
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
            Connection banners
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3 rounded-2xl bg-ink px-4 py-3 text-white">
              <Icon name="off" className="h-5 w-5" />
              <span className="text-sm font-bold">You’re offline</span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-amber px-4 py-3 text-ink">
              <Icon name="wifi" className="h-5 w-5 [animation:sco-pulse_1.2s_ease-in-out_infinite]" />
              <span className="text-sm font-bold">Reconnecting…</span>
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-berry px-4 py-3 text-white">
              <Icon name="off" className="h-5 w-5" />
              <span className="flex-1 text-sm font-bold">Network error</span>
              <span className="rounded-lg bg-white/20 px-3 py-1 text-xs font-bold">
                Retry
              </span>
            </div>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">
            Order status badges
          </p>
          <div className="flex flex-wrap gap-2 rounded-3xl bg-card p-4 shadow-sm">
            {(
              [
                'Queued',
                'Preparing',
                'Ready',
                'Completed',
                'Delayed',
                'Cancelled',
              ] as OrderStatus[]
            ).map((s) => (
              <StatusBadge key={s} status={s} />
            ))}
          </div>
        </div>
      </div>
    </Screen>
  )
}

/* -------------------------------- Root ------------------------------------ */

const SCREEN_LIST: { key: Screen; label: string }[] = [
  { key: 'login', label: '1 · Login' },
  { key: 'home', label: '2 · Home' },
  { key: 'menu', label: '3 · Menu' },
  { key: 'details', label: '4 · Item' },
  { key: 'cart', label: '5 · Cart' },
  { key: 'checkout', label: '6 · Checkout' },
  { key: 'confirm', label: '7 · Confirmed' },
  { key: 'tracking', label: '8 · Tracking' },
  { key: 'ready', label: '9 · Ready' },
  { key: 'history', label: '10 · Orders' },
  { key: 'orderDetails', label: '11 · Order' },
  { key: 'notifications', label: '12 · Alerts' },
  { key: 'profile', label: '13 · Profile' },
  { key: 'states', label: '＋ States' },
]

function Device({ children, animKey, slideDir }: { children: ReactNode; animKey: number; slideDir: 'forward' | 'back' }) {
  const { toast } = useStore()
  return (
    <div className="relative">
      <div
        className="relative overflow-hidden rounded-[3rem] bg-paper shadow-[0_40px_80px_-20px_rgba(0,0,0,0.45)] ring-1 ring-black/10"
        style={{ width: 390, height: 844 }}
      >
        {/* notch */}
        <div className="pointer-events-none absolute left-1/2 top-2 z-30 h-6 w-32 -translate-x-1/2 rounded-full bg-ink" />
        <div
          key={animKey}
          className="h-full"
          style={{
            animation: `${slideDir === 'forward' ? 'sco-slide-in' : 'sco-slide-back'} 0.26s cubic-bezier(0.25,0.46,0.45,0.94) both`,
          }}
        >
          {children}
        </div>
        <ToastBanner />
      </div>
    </div>
  )
}

export default function App() {
  const [appMode, setAppMode] = useState<'admin' | 'mobile-preview'>('admin')
  const [screen, setScreen] = useState<Screen>('login')
  const [user, setUser] = useState<UserProfile | null>(() => apiClient.getCachedUser())
  const [animKey, setAnimKey] = useState(0)
  const [slideDir, setSlideDir] = useState<'forward' | 'back'>('forward')
  const [cart, setCart] = useState<CartLine[]>([
    { item: MENU[0], qty: 1 },
    { item: MENU[3], qty: 1 },
    { item: MENU[5], qty: 1 },
  ])
  const [selected, setSelected] = useState<MenuItem | null>(MENU[0])
  const [banner, setBanner] = useState<SystemBanner | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = (msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), 2500)
  }

  // Check auth session on startup
  useEffect(() => {
    apiClient.getMe().then((res) => {
      if (res.user) {
        setUser(res.user)
      }
    })
  }, [])

  const loginUser = async (roll: string, passcode: string): Promise<AuthResponse> => {
    const res = await apiClient.login(roll, passcode)
    if (res.success && res.user) {
      setUser(res.user)
      showToast(res.message || `Welcome back, ${res.user.name}!`)
      const nextDepth = DEPTH['home'] ?? 1
      const curDepth = DEPTH[screen] ?? 0
      setSlideDir(nextDepth >= curDepth ? 'forward' : 'back')
      setAnimKey((k) => k + 1)
      setScreen('home')
    }
    return res
  }

  const registerUser = async (input: RegisterInput): Promise<AuthResponse> => {
    const res = await apiClient.register(input)
    if (res.success && res.user) {
      setUser(res.user)
      showToast(res.message || `Welcome, ${res.user.name}!`)
      const nextDepth = DEPTH['home'] ?? 1
      const curDepth = DEPTH[screen] ?? 0
      setSlideDir(nextDepth >= curDepth ? 'forward' : 'back')
      setAnimKey((k) => k + 1)
      setScreen('home')
    }
    return res
  }

  const logoutUser = async () => {
    await apiClient.logout()
    setUser(null)
    showToast('Logged out successfully')
    const nextDepth = DEPTH['login'] ?? 0
    const curDepth = DEPTH[screen] ?? 1
    setSlideDir(nextDepth >= curDepth ? 'forward' : 'back')
    setAnimKey((k) => k + 1)
    setScreen('login')
  }

  const store: Store = useMemo(() => {
    const cartCount = cart.reduce((a, l) => a + l.qty, 0)
    const cartTotal = cart.reduce((a, l) => a + l.qty * l.item.price, 0)
    return {
      screen,
      go: (s) => {
        const nextDepth = DEPTH[s] ?? 1
        const curDepth = DEPTH[screen] ?? 1
        setSlideDir(nextDepth >= curDepth ? 'forward' : 'back')
        setAnimKey((k) => k + 1)
        setScreen(s)
      },
      user,
      loginUser,
      registerUser,
      logoutUser,
      cart,
      add: (item, qty = 1) => {
        setCart((c) => {
          const ex = c.find((l) => l.item.id === item.id)
          if (ex)
            return c.map((l) =>
              l.item.id === item.id ? { ...l, qty: l.qty + qty } : l
            )
          return [...c, { item, qty }]
        })
        showToast(`${item.emoji} ${item.name} added`)
      },
      setQty: (id, qty) =>
        setCart((c) =>
          qty <= 0
            ? c.filter((l) => l.item.id !== id)
            : c.map((l) => (l.item.id === id ? { ...l, qty } : l))
        ),
      clear: () => setCart([]),
      cartCount,
      cartTotal,
      selected,
      select: setSelected,
      banner,
      setBanner,
      toast,
      showToast,
    }
  }, [screen, user, cart, selected, banner, toast])

  const screens: Record<Screen, ReactNode> = {
    login: <LoginScreen />,
    home: <HomeScreen />,
    menu: <MenuScreen />,
    details: <DetailsScreen />,
    cart: <CartScreen />,
    checkout: <CheckoutScreen />,
    confirm: <ConfirmScreen />,
    tracking: <TrackingScreen />,
    ready: <ReadyScreen />,
    history: <HistoryScreen />,
    orderDetails: <OrderDetailsScreen />,
    notifications: <NotificationsScreen />,
    profile: <ProfileScreen />,
    states: <StatesScreen />,
  }

  // Render Admin Dashboard by default
  if (appMode === 'admin') {
    return (
      <AdminDashboard
        appMode={appMode}
        onToggleMode={() => setAppMode('mobile-preview')}
      />
    )
  }

  // Render Mobile Preview when toggled
  return (
    <Ctx.Provider value={store}>
      <div className="relative min-h-screen bg-[#DED4C7] p-4 lg:p-10 flex flex-col items-center justify-center">
        {/* Top return banner */}
        <div className="mb-6 flex items-center gap-4 bg-white/90 backdrop-blur-md px-5 py-2.5 rounded-full border border-[#E5DFD7] shadow-sm">
          <span className="text-xs font-bold text-[#1D1A16]">📱 Student Mobile Preview Mode</span>
          <button
            onClick={() => setAppMode('admin')}
            className="px-4 py-1.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-sm cursor-pointer"
          >
            ← Return to Admin Dashboard
          </button>
        </div>

        <div className="flex w-full flex-col items-center gap-6 lg:flex-row lg:items-start lg:justify-center lg:gap-12">
          {/* Screen jumper */}
          <aside className="order-2 w-full max-w-[390px] lg:order-1 lg:w-52 lg:max-w-none">
            <div className="rounded-3xl border border-black/10 bg-white/70 p-4 backdrop-blur">
              <p className="mb-1 font-display text-sm font-extrabold">
                Smart Canteen OS
              </p>
              <p className="mb-3 text-[11px] text-ink-soft">
                Student app · tap to jump between screens
              </p>
              <div className="grid grid-cols-2 gap-1.5 lg:grid-cols-1">
                {SCREEN_LIST.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => setScreen(s.key)}
                    className={`rounded-xl px-3 py-2 text-left text-xs font-semibold transition-colors ${
                      screen === s.key
                        ? 'bg-tangerine text-white'
                        : 'bg-white text-ink hover:bg-black/[0.04]'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <div className="order-1 lg:order-2">
            <Device animKey={animKey} slideDir={slideDir}>{screens[screen]}</Device>
          </div>
        </div>
      </div>
    </Ctx.Provider>
  )
}
