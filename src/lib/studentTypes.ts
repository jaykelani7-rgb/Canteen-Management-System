export interface UserProfile {
  id: string; rollNumber: string; name: string; branch: string; email: string; phone: string;
  walletBalance: number; upiId: string; totalOrders: number; totalSpent: number;
  savedMinutes: number; createdAt: string | null; dietaryPreference?: string; favorites?: string[];
}
export interface AuthResponse { success: boolean; message: string; user?: UserProfile; token?: string }
export interface RegisterInput { rollNumber: string; name: string; passcode: string; branch?: string; phone?: string; email?: string }
export interface StudentMenuItem {
  id: string; name: string; desc: string; price: number; rating: number; prepMins: number;
  category: 'Snacks' | 'Meals' | 'Beverages'; veg: boolean; available: boolean; tag?: string;
  emoji: string; photo: string; calories?: number;
  customizations?: { name: string; price: number }[];
}
export type StudentOrderStatus = 'Queued' | 'Preparing' | 'Ready' | 'Picked Up' | 'Completed' | 'Delayed' | 'Cancelled'
export interface StudentOrder {
  id: string; orderId: number; number: string; studentId: string;
  items: { id: string; name: string; qty: number; price: number; photo?: string; customizations?: string[] }[];
  itemTotal: number; packagingFee: number; gst: number; total: number; paymentMethod: string;
  status: StudentOrderStatus; payment: 'Paid' | 'Failed' | 'Refunded'; pickupCounter: string; pickupToken: string;
  queuePosition: number; prepTimeMinutes: number; estimatedReadyAt?: string; date: string;
  createdAt?: string; readyAt?: string; completedAt?: string; cancellationReason?: string; qrCodeData: string;
}
export interface OrderTracking {
  orderNumber: string; status: StudentOrderStatus; queuePosition: number; ordersAhead: number;
  countdownSeconds: number; countdownMinutesFormatted: string; estimatedReadyTime: string;
  progressPercent: number; pickupCounter: string; pickupToken: string; activeStepIndex: number;
  timeline: { key: string; label: string; note: string; done: boolean; active: boolean }[];
}
export interface StudentNotification {
  id: number; title: string; subtitle: string; emoji: string; color: string; unread: boolean;
  time: string; orderId?: number;
}
export interface WalletTransaction {
  id: string; amount: number; type: string; paymentMethod: string; description: string;
  status: string; createdAt?: string; dateFormatted?: string;
}
