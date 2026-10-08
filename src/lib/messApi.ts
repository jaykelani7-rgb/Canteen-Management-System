export type Meal = 'Breakfast' | 'Lunch' | 'Snacks' | 'Dinner'
export interface MessPlan { id: 'single' | 'double'; name: string; amount: number; tokens: number; duration_days: number; is_active: boolean }
export interface MessSubscription {
  id: number; student_id: string | null; student_name: string; roll_number: string; year: string; branch: string;
  mobile_number: string; plan_type: 'single' | 'double'; amount_paid: number; total_tokens: number; remaining_tokens: number;
  start_date: string; end_date: string; status: 'Active' | 'Expired' | 'Exhausted' | 'Cancelled';
  payment_method: string; payment_reference: string | null; notes: string | null; tokens_used: number;
}
export type MessInput = Omit<MessSubscription, 'id' | 'student_id' | 'remaining_tokens' | 'status' | 'tokens_used'>
export interface Attendance {
  id: number; subscription_id: number; meal_date: string; meal_type: Meal; status: 'Taken' | 'Reversed';
  token_before: number; token_after: number; marked_at: string; marked_by: string | null; undo_reason: string | null;
  reversed_at: string | null; reversed_by_admin_id: number | null; reversal_token_before: number | null; reversal_token_after: number | null;
}
export interface MessDetail extends MessSubscription { attendance: Attendance[]; meals_taken: number }
export interface DailyRow { subscription: MessSubscription; attendance: Attendance | null; eligible: boolean; can_mark: boolean }
export interface MessStats {
  total_active_members: number; eligible_members: number; meals_taken: number; meals_remaining: number;
  tokens_consumed: number; tokens_consumed_today: number; low_token_members: number; zero_token_members: number; expired_memberships: number;
}
const query = (values: Record<string, string>) => '?' + new URLSearchParams(Object.entries(values).filter(([, value]) => value !== '')).toString()
export const messApi = {
  getMessSubscriptions: (filters: Record<string, string> = {}) => request<MessSubscription[]>('/mess/subscriptions' + query(filters)),
  createMessSubscription: (body: MessInput) => request<MessSubscription>('/mess/subscriptions', 'POST', body),
  updateMessSubscription: (id: number, body: MessInput & { status: 'Active' | 'Cancelled' }) => request<MessSubscription>(`/mess/subscriptions/${id}`, 'PUT', body),
  getMessSubscription: (id: number) => request<MessDetail>(`/mess/subscriptions/${id}`),
  getMessAttendance: (filters: Record<string, string>) => request<DailyRow[]>('/mess/attendance' + query(filters)),
  markMealTaken: (subscription_id: number, meal_date: string, meal_type: Meal) => request<{ attendance: Attendance; subscription: MessSubscription }>('/mess/attendance/mark', 'POST', { subscription_id, meal_date, meal_type }),
  undoMealAttendance: (id: number, reason: string) => request<{ attendance: Attendance; subscription: MessSubscription }>(`/mess/attendance/${id}/undo`, 'POST', { reason }),
  getMessStats: (filters: Record<string, string>) => request<MessStats>('/mess/stats' + query(filters)),
  getMessPlans: () => request<MessPlan[]>('/mess/plans'),
  updateMessPlan: (id: string, body: Omit<MessPlan, 'id'>) => request<MessPlan>(`/mess/plans/${id}`, 'PUT', body),
}
import { adminRequest as request } from './adminApi'
export { AdminApiError as MessApiError } from './adminApi'
