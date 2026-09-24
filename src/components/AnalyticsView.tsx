import React from 'react'

export default function AnalyticsView() {
  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div>
        <h3 className="text-xl font-bold text-[#1D1A16] tracking-tight">
          Canteen Operations & Sales Analytics
        </h3>
        <p className="text-xs text-stone-500 mt-1">
          High-concurrency daily footfall, revenue metrics, and food consumption trends.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Daily Revenue</p>
          <h4 className="text-2xl font-extrabold text-[#1D1A16] mt-1">₹48,920</h4>
          <p className="text-[11px] text-emerald-700 font-semibold mt-1">↑ +14.2% from yesterday</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Active Students</p>
          <h4 className="text-2xl font-extrabold text-[#1D1A16] mt-1">1,420</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">Peak: 12:45 - 13:30 (Lunch)</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Redis Cache Hit</p>
          <h4 className="text-2xl font-extrabold text-emerald-700 mt-1">99.4%</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">&lt; 3ms response time</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Waste Reduction</p>
          <h4 className="text-2xl font-extrabold text-[#F25C2C] mt-1">-28%</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">Smart count forecasting</p>
        </div>
      </div>

      {/* Popular Items breakdown */}
      <div className="p-8 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm space-y-4">
        <h4 className="text-base font-bold text-[#1D1A16]">
          Top Selling A La Carte Items (Today)
        </h4>

        <div className="space-y-3">
          {[
            { name: 'Cold Coffee with Ice Cream', orders: 92, pct: 92, rev: '₹6,900' },
            { name: 'Crispy Peri-Peri French Fries', orders: 78, pct: 78, rev: '₹6,630' },
            { name: 'Chicken Tikka Roll (Double Egg)', orders: 56, pct: 56, rev: '₹8,400' },
            { name: 'Paneer Butter Masala (Single)', orders: 42, pct: 42, rev: '₹6,720' },
          ].map((dish, i) => (
            <div key={i} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-[#1D1A16]">{dish.name}</span>
                <span className="font-mono text-stone-600">
                  {dish.orders} orders ({dish.rev})
                </span>
              </div>
              <div className="w-full h-2.5 rounded-full bg-stone-100 overflow-hidden">
                <div
                  className="h-full bg-[#F25C2C] rounded-full transition-all duration-500"
                  style={{ width: `${dish.pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
