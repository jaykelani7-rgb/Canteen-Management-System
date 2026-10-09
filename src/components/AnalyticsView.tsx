import React, { useEffect, useState } from 'react'
import { adminOperationsApi, type AdminAnalytics } from '../lib/adminOperationsApi'

export default function AnalyticsView() {
  const [data, setData] = useState<AdminAnalytics | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    adminOperationsApi.analytics().then(result => { if (active) setData(result) }).catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false }
  }, [])
  const money = (value: number) => value.toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
  const change = data && data.yesterdayRevenue > 0 ? ((data.dailyRevenue - data.yesterdayRevenue) / data.yesterdayRevenue * 100).toFixed(1) + '% from yesterday' : 'No prior revenue baseline'
  const topItems = (data?.topItems || []).map(item => ({ name: item.name, orders: item.quantity, rev: money(item.revenue), pct: item.quantity / Math.max(1, ...((data?.topItems || []).map(row => row.quantity))) * 100 }))

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

      {error && <p role="alert" className="rounded-2xl bg-white p-4 text-sm text-red-700 border border-red-200">{error}</p>}
      {!data && !error && <p role="status" className="text-sm text-stone-500">Loading analytics…</p>}
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Daily Revenue</p>
          <h4 className="text-2xl font-extrabold text-[#1D1A16] mt-1">{data ? money(data.dailyRevenue) : '—'}</h4>
          <p className="text-[11px] text-emerald-700 font-semibold mt-1">{change}</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Active Students</p>
          <h4 className="text-2xl font-extrabold text-[#1D1A16] mt-1">{data ? data.activeStudents.toLocaleString('en-IN') : '—'}</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">{data ? data.totalOrders + ' orders today · ' + data.activeOrders + ' active' : 'Awaiting backend data'}</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Redis Cache Hit</p>
          <h4 className="text-2xl font-extrabold text-emerald-700 mt-1">{data?.redisCacheHitPercent == null ? 'Unavailable' : data.redisCacheHitPercent + '%'}</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">Measured cache telemetry is not configured</p>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-600">Waste Reduction</p>
          <h4 className="text-2xl font-extrabold text-[#F25C2C] mt-1">{data?.wasteReductionPercent == null ? 'Unavailable' : data.wasteReductionPercent + '%'}</h4>
          <p className="text-[11px] text-stone-500 font-medium mt-1">Waste measurements are not configured</p>
        </div>
      </div>

      {/* Popular Items breakdown */}
      <div className="p-8 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm space-y-4">
        <h4 className="text-base font-bold text-[#1D1A16]">
          Top Selling A La Carte Items (Today)
        </h4>

        <div className="space-y-3">
          {data && !topItems.length && <p className="text-sm text-stone-500">No paid item sales today.</p>}
          {topItems.map((dish, i) => (
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
