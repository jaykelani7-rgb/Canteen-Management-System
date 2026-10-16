import type { StudentLunchMenu } from './studentTypes'

// Used only while service metadata is unavailable; ordering always follows the API.
export const RUSH_FALLBACK_STARTS = { lunch: '12:00', dinner: '19:00' } as const
const INDIA_TIME_ZONE = 'Asia/Kolkata'
type Schedule = Pick<StudentLunchMenu, 'serviceStart' | 'serviceWindow'> | null
function startMinutes(meal: 'lunch' | 'dinner', schedule: Schedule): number {
  const raw = schedule?.serviceStart || schedule?.serviceWindow?.split(/\s*[-–]\s*/)[0]
  const valid = typeof raw === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(raw.trim())
  const [hours, minutes] = (valid ? raw!.trim() : RUSH_FALLBACK_STARTS[meal]).split(':').map(Number)
  return hours * 60 + minutes
}
export function nextRush(now: Date, lunch: Schedule = null, dinner: Schedule = null) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: INDIA_TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(now)
  const value = (name: string) => Number(parts.find(part => part.type === name)?.value || 0)
  const current = value('hour') * 60 + value('minute') + value('second') / 60
  const targets = [
    { meal: 'lunch' as const, start: startMinutes('lunch', lunch) },
    { meal: 'dinner' as const, start: startMinutes('dinner', dinner) },
  ].sort((a, b) => a.start - b.start)
  const upcoming = targets.find(target => target.start > current)
  const target = upcoming || targets[0]
  const tomorrow = !upcoming
  const hours = Math.floor(target.start / 60), minutes = target.start % 60
  const time = `${hours % 12 || 12}${minutes ? ':' + String(minutes).padStart(2, '0') : ''} ${hours >= 12 ? 'PM' : 'AM'}`
  return { meal: target.meal, startMinutes: target.start, tomorrow, time,
    title: tomorrow ? `Beat tomorrow’s ${time} ${target.meal} rush` : `Beat the ${time} ${target.meal} rush`,
    description: tomorrow ? 'Plan tomorrow’s meal. Check the menu for availability.' : 'Browse the menu and plan your pickup when service opens.' }
}
