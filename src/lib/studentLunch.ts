import type { StudentLunchMenu, StudentMenuItem, StudentOrderItemInput } from './studentTypes'

export const CHAPATI_BHAJI_ID = 'lunch-chapati-bhaji'
export const THALI_ID = 'lunch-thali'
export const DINNER_CHAPATI_BHAJI_ID = 'dinner-chapati-bhaji'
export const DINNER_THALI_ID = 'dinner-thali'
export type BundleMeal = 'lunch' | 'dinner'
export const isChapatiItem = (id: string) => id === CHAPATI_BHAJI_ID || id === DINNER_CHAPATI_BHAJI_ID
// Keep existing helper names compatible while sharing both meal implementations.
export const isLunchItem = (id: string) => isChapatiItem(id) || id === THALI_ID || id === DINNER_THALI_ID
export const bundleMeal = (item: StudentMenuItem): BundleMeal => item.id.startsWith('dinner-') ? 'dinner' : 'lunch'
export const mealLabel = (meal: BundleMeal) => meal === 'dinner' ? 'Dinner' : 'Lunch'
export const lunchLineKey = (item: StudentMenuItem, sabjiChoice?: string) => item.lunch
  ? JSON.stringify([item.id, bundleMeal(item), item.lunch.date, item.lunch.revision, sabjiChoice || '']) : item.id
export function lunchItems(menu: StudentLunchMenu): StudentMenuItem[] {
  return menu.options.filter(option => isLunchItem(option.id) && option.id.startsWith(menu.mealType + '-')).map(option => ({
    ...option, desc: isChapatiItem(option.id)
      ? '3 chapatis + salad + your choice of 1 sabji' : menu.contents.join(' · ') || `Complete meal from today’s ${menu.mealType} menu`,
    rating: 0, prepMins: 10, category: 'Meals', veg: true, available: menu.available && option.available !== false,
    emoji: '🍽️', photo: '', tag: `Today’s ${menu.mealType}`,
    lunch: { mealType: menu.mealType, serviceWindow: menu.serviceWindow, date: menu.date, revision: menu.mealRevision, contents: menu.contents,
      sabjiOptions: menu.sabjiOptions, unavailableReason: option.available === false ? option.unavailableReason || menu.unavailableReason : menu.unavailableReason },
  }))
}
export function lunchCartError(lines: { item: StudentMenuItem; sabjiChoice?: string }[], menu: StudentLunchMenu | null): string | null {
  const meals = lines.filter(line => isLunchItem(line.item.id) && (!menu || bundleMeal(line.item) === menu.mealType))
  if (!meals.length) return null
  const period = menu?.mealType || bundleMeal(meals[0].item), label = mealLabel(period)
  if (!menu) return `${label} could not be verified. Refresh the menu before ordering.`
  if (!menu.available) return menu.unavailableReason || `${label} is currently unavailable.`
  for (const line of meals) {
    const current = menu.options.find(option => option.id === line.item.id)
    if (!current || !line.item.lunch || line.item.lunch.date !== menu.date || !menu.mealRevision || line.item.lunch.revision !== menu.mealRevision || line.item.price !== current.price)
      return `Today’s ${period} menu has changed. Remove the old ${period} items and choose again from the refreshed menu.`
    if (current.available === false) return current.unavailableReason || `This ${period} option is currently unavailable.`
    if (isChapatiItem(line.item.id) && (!line.sabjiChoice || menu.sabjiOptions.length < 1 || !menu.sabjiOptions.includes(line.sabjiChoice)))
      return 'Choose exactly one available sabji for Chapati Bhaji.'
  }
  return null
}
export function mealCartError(lines: { item: StudentMenuItem; sabjiChoice?: string }[], lunch: StudentLunchMenu | null, dinner: StudentLunchMenu | null): string | null {
  for (const [period, menu] of [['lunch', lunch], ['dinner', dinner]] as const) {
    const problem = lunchCartError(lines.filter(line => bundleMeal(line.item) === period), menu)
    if (problem) return problem
  }
  return null
}
export function lunchOrderInput(line: { item: StudentMenuItem; qty: number; sabjiChoice?: string }): StudentOrderItemInput {
  return { id: line.item.id, qty: line.qty,
    ...(line.item.lunch ? { mealRevision: line.item.lunch.revision || '', ...(line.sabjiChoice ? { sabjiChoice: line.sabjiChoice } : {}) } : {}) }
}
export function lunchContents(item: StudentMenuItem, sabjiChoice?: string): string[] {
  return isChapatiItem(item.id) ? ['3 chapatis', 'Salad', ...(sabjiChoice ? [sabjiChoice] : [])] : item.lunch?.contents || []
}
