import type { StudentLunchMenu } from './studentTypes'

const INDIA_TIME_ZONE = 'Asia/Kolkata'
type Schedule = Pick<StudentLunchMenu, 'serviceStart' | 'serviceWindow'> | null

// Promotional windows are independent of server-authoritative ordering hours.
// Keep optional schedule arguments compatible with existing callers.
export function nextRush(now: Date, _lunch: Schedule = null, _dinner: Schedule = null) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: INDIA_TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(now)
  const value = (name: string) => Number(parts.find(part => part.type === name)?.value || 0)
  const current = value('hour') * 60 + value('minute') + value('second') / 60
  const meal = current >= 600 && current < 720 ? 'lunch'
    : current >= 1080 && current < 1140 ? 'dinner' : null
  if (!meal) return null
  const time = meal === 'lunch' ? '12 PM' : '7 PM'
  return { meal, time, title: `Beat the ${time} ${meal} rush`,
    description: 'Browse the menu and plan your pickup when service opens.' }
}
