import React, { useState } from 'react'

export interface OrderItem {
  id: string
  token_number: string
  student_name: string
  roll_no: string
  items: { name: string; qty: number; price: number }[]
  total_amount: number
  status: 'Received' | 'Preparing' | 'Ready' | 'Completed'
  order_time: string
  prep_timer_mins: number
}

interface LiveOrdersViewProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

const INITIAL_ORDERS: OrderItem[] = [
  {
    id: 'ord-101',
    token_number: '#A-104',
    student_name: 'Rahul Sharma',
    roll_no: 'CS-2023-42',
    items: [
      { name: 'Paneer Butter Masala (Single)', qty: 1, price: 160 },
      { name: 'Cold Coffee with Ice Cream', qty: 2, price: 150 },
    ],
    total_amount: 310,
    status: 'Preparing',
    order_time: '13:18',
    prep_timer_mins: 4,
  },
  {
    id: 'ord-102',
    token_number: '#A-105',
    student_name: 'Priya Patel',
    roll_no: 'EC-2024-11',
    items: [
      { name: 'Crispy Peri-Peri French Fries', qty: 1, price: 85 },
      { name: 'Double Masala Cheese Maggi', qty: 1, price: 65 },
    ],
    total_amount: 150,
    status: 'Ready',
    order_time: '13:12',
    prep_timer_mins: 0,
  },
  {
    id: 'ord-103',
    token_number: '#A-106',
    student_name: 'Ananya Verma',
    roll_no: 'ME-2023-89',
    items: [
      { name: 'Chicken Tikka Roll (Double Egg)', qty: 2, price: 300 },
      { name: 'Fresh Mosambi Orange Juice', qty: 1, price: 60 },
    ],
    total_amount: 360,
    status: 'Received',
    order_time: '13:22',
    prep_timer_mins: 12,
  },
  {
    id: 'ord-104',
    token_number: '#A-107',
    student_name: 'Vikram Singh',
    roll_no: 'EE-2022-04',
    items: [{ name: 'Veg Cheese Grill Sandwich', qty: 2, price: 220 }],
    total_amount: 220,
    status: 'Received',
    order_time: '13:24',
    prep_timer_mins: 8,
  },
]

export default function LiveOrdersView({ onShowToast }: LiveOrdersViewProps) {
  const [orders, setOrders] = useState<OrderItem[]>(INITIAL_ORDERS)
  const [selectedStatusTab, setSelectedStatusTab] = useState<string>('All')

  const handleAdvanceStatus = (orderId: string) => {
    setOrders((prev) =>
      prev.map((order) => {
        if (order.id === orderId) {
          let nextStatus: OrderItem['status'] = 'Completed'
          if (order.status === 'Received') nextStatus = 'Preparing'
          else if (order.status === 'Preparing') nextStatus = 'Ready'
          else if (order.status === 'Ready') nextStatus = 'Completed'

          onShowToast?.(
            `Order ${order.token_number} Updated`,
            `Status moved to "${nextStatus}". Student notified on app.`,
            'success'
          )
          return { ...order, status: nextStatus }
        }
        return order
      })
    )
  }

  const filteredOrders = orders.filter((order) => {
    if (selectedStatusTab === 'All') return true
    return order.status === selectedStatusTab
  })

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-[#1D1A16] tracking-tight">
            Live Kitchen Order Queue
          </h3>
          <p className="text-xs text-stone-500 mt-1">
            Real-time student food orders received from student mobile app and digital tokens.
          </p>
        </div>

        {/* Status filters */}
        <div className="flex items-center gap-1.5 p-1 rounded-full bg-white border border-[#E5DFD7] shadow-2xs">
          {['All', 'Received', 'Preparing', 'Ready', 'Completed'].map((tab) => {
            const isSelected = selectedStatusTab === tab
            return (
              <button
                key={tab}
                onClick={() => setSelectedStatusTab(tab)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-[#F25C2C] text-white shadow-sm'
                    : 'text-stone-600 hover:text-stone-900'
                }`}
              >
                {tab}
              </button>
            )
          })}
        </div>
      </div>

      {/* Orders Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredOrders.map((order) => {
          const statusColors: Record<OrderItem['status'], { badge: string; border: string }> = {
            Received: { badge: 'bg-stone-100 text-stone-700 border-stone-200', border: 'border-[#E5DFD7]' },
            Preparing: { badge: 'bg-amber-50 text-amber-800 border-amber-200', border: 'border-amber-300' },
            Ready: { badge: 'bg-emerald-50 text-emerald-800 border-emerald-200', border: 'border-emerald-300' },
            Completed: { badge: 'bg-stone-100 text-stone-400 border-stone-200', border: 'border-stone-200' },
          }

          return (
            <div
              key={order.id}
              className={`p-6 rounded-3xl bg-white border ${statusColors[order.status].border} shadow-sm flex flex-col justify-between space-y-6 hover:shadow-md transition-all`}
            >
              <div>
                {/* Token & Status Header */}
                <div className="flex items-center justify-between pb-4 border-b border-[#E5DFD7]">
                  <div className="flex items-center gap-2.5">
                    <span className="text-lg font-mono font-extrabold text-[#F25C2C]">
                      {order.token_number}
                    </span>
                    <span className="text-[11px] font-mono text-stone-500">
                      {order.order_time}
                    </span>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold border ${statusColors[order.status].badge}`}
                  >
                    {order.status}
                  </span>
                </div>

                {/* Student Info */}
                <div className="mt-3">
                  <h5 className="text-sm font-bold text-[#1D1A16]">{order.student_name}</h5>
                  <p className="text-[11px] font-mono text-stone-500">{order.roll_no}</p>
                </div>

                {/* Items List */}
                <div className="mt-4 space-y-2">
                  {order.items.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-xs font-semibold text-stone-800"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded-md bg-[#FAF7F3] border border-[#E5DFD7] text-[10px] font-bold flex items-center justify-center text-stone-600">
                          {item.qty}x
                        </span>
                        <span className="truncate max-w-[180px]">{item.name}</span>
                      </div>
                      <span className="font-mono text-stone-500">₹{item.price}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bottom Total & Action */}
              <div className="pt-4 border-t border-[#E5DFD7] flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase font-bold text-stone-600">Total Bill</p>
                  <p className="text-base font-bold text-[#1D1A16]">₹{order.total_amount}</p>
                </div>

                {order.status !== 'Completed' ? (
                  <button
                    onClick={() => handleAdvanceStatus(order.id)}
                    className="px-4 py-2 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-sm active:scale-95 cursor-pointer flex items-center gap-1.5"
                  >
                    <span>
                      {order.status === 'Received'
                        ? 'Start Cooking →'
                        : order.status === 'Preparing'
                        ? 'Mark Ready ✓'
                        : 'Complete & Handover'}
                    </span>
                  </button>
                ) : (
                  <span className="text-xs font-bold text-stone-400">Order Completed</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
