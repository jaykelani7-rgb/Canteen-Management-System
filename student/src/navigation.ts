export type StudentScreen =
  | 'login' | 'home' | 'menu' | 'details' | 'cart' | 'checkout'
  | 'confirm' | 'tracking' | 'ready' | 'history' | 'orderDetails'
  | 'notifications' | 'profile' | 'wallet'

/** React screens do not create WebView history entries. Keep their Back path here. */
export function createStudentNavigation(publish: (screen: StudentScreen) => void) {
  let path: StudentScreen[] = ['login']
  const reset = (screen: StudentScreen) => { path = [screen]; publish(screen) }
  const go = (screen: StudentScreen) => {
    if (screen === 'login' || screen === 'home') { reset(screen); return }
    // A paid/pending order must never lead Back into its old checkout form.
    if (screen === 'confirm' || screen === 'tracking' || screen === 'ready') {
      path = ['home', screen]
    } else {
      const prior = path.lastIndexOf(screen)
      path = prior < 0 ? [...path, screen] : path.slice(0, prior + 1)
    }
    publish(screen)
  }
  const back = () => {
    const current = path[path.length - 1]
    if (current === 'login' || current === 'home') return false
    if (current === 'checkout') { go('cart'); return true }
    const previous = path[path.length - 2]
    // Never return to a logged-out screen or a stale payment form.
    if (previous && previous !== 'login' && previous !== 'checkout') {
      path.pop(); publish(previous)
    } else {
      go(current === 'details' ? 'menu' : current === 'wallet' ? 'profile' : current === 'orderDetails' ? 'history' : 'home')
    }
    return true
  }
  return { go, back, reset }
}
