import type { StudentLunchMenu, StudentMenuItem, StudentOrderItemInput } from './studentTypes'

export const CHAPATI_BHAJI_ID = 'lunch-chapati-bhaji'
export const THALI_ID = 'lunch-thali'
export const isLunchItem = (id: string) => id === CHAPATI_BHAJI_ID || id === THALI_ID
export const lunchLineKey = (item: StudentMenuItem, sabjiChoice?: string) => item.lunch
  ? JSON.stringify([item.id, item.lunch.date, item.lunch.revision, sabjiChoice || '']) : item.id
export function lunchItems(menu: StudentLunchMenu): StudentMenuItem[] {
  return menu.options.filter(option => isLunchItem(option.id)).map(option => ({
    ...option, desc: option.id === CHAPATI_BHAJI_ID
      ? '3 chapatis + salad + your choice of 1 sabji' : menu.contents.join(' · ') || 'Complete meal from today’s lunch menu',
    rating: 0, prepMins: 10, category: 'Meals', veg: true, available: menu.available && option.available !== false,
    emoji: '🍽️', photo: '', tag: 'Today’s lunch',
    lunch: { date: menu.date, revision: menu.mealRevision, contents: menu.contents,
      sabjiOptions: menu.sabjiOptions, unavailableReason: option.available === false ? option.unavailableReason || menu.unavailableReason : menu.unavailableReason },
  }))
}
export function lunchCartError(lines: { item: StudentMenuItem; sabjiChoice?: string }[], menu: StudentLunchMenu | null): string | null {
  const lunch = lines.filter(line => isLunchItem(line.item.id))
  if (!lunch.length) return null
  if (!menu) return 'Lunch could not be verified. Refresh the menu before ordering.'
  if (!menu.available) return menu.unavailableReason || 'Lunch is currently unavailable.'
  for (const line of lunch) {
    const current = menu.options.find(option => option.id === line.item.id)
    if (!current || !line.item.lunch || line.item.lunch.date !== menu.date || !menu.mealRevision || line.item.lunch.revision !== menu.mealRevision || line.item.price !== current.price)
      return 'Today’s lunch menu has changed. Remove the old lunch items and choose again from the refreshed menu.'
    if (current.available === false) return current.unavailableReason || 'This lunch option is currently unavailable.'
    if (line.item.id === CHAPATI_BHAJI_ID && (!line.sabjiChoice || menu.sabjiOptions.length < 1 || !menu.sabjiOptions.includes(line.sabjiChoice)))
      return 'Choose exactly one available sabji for Chapati Bhaji.'
  }
  return null
}
export function lunchOrderInput(line: { item: StudentMenuItem; qty: number; sabjiChoice?: string }): StudentOrderItemInput {
  return { id: line.item.id, qty: line.qty,
    ...(line.item.lunch ? { mealRevision: line.item.lunch.revision || '', ...(line.sabjiChoice ? { sabjiChoice: line.sabjiChoice } : {}) } : {}) }
}
export function lunchContents(item: StudentMenuItem, sabjiChoice?: string): string[] {
  return item.id === CHAPATI_BHAJI_ID ? ['3 chapatis', 'Salad', ...(sabjiChoice ? [sabjiChoice] : [])] : item.lunch?.contents || []
}
