import React, { useEffect, useRef, useState } from 'react'
import { adminOperationsApi, type CatalogueItem } from '../lib/adminOperationsApi'

export interface AlaCarteItem {
  id: string
  item_name: string
  category: 'Snacks' | 'Meals' | 'Beverages' | 'Desserts' | 'Quick Bites'
  price: number
  timing_window: string
  is_available: boolean
  veg: boolean
  orders_today: number | null
  prep_time_mins: number
  source: CatalogueItem
  emoji?: string
}

interface AlaCarteManagementProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

function toInventoryItem(item: CatalogueItem): AlaCarteItem {
  return { id: item.id, item_name: item.name, category: item.category, price: item.price, timing_window: item.timingWindow,
    is_available: item.available, veg: item.veg, orders_today: item.ordersToday ?? null, prep_time_mins: item.prepMins, emoji: item.emoji, source: item }
}

export default function AlaCarteManagement({ onShowToast }: AlaCarteManagementProps) {
  const [items, setItems] = useState<AlaCarteItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('All')
  const [selectedTimingFilter, setSelectedTimingFilter] = useState<string>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<AlaCarteItem | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const mutationLock = useRef(false)
  const [formDescription, setFormDescription] = useState('')
  const [formPrep, setFormPrep] = useState('10')
  useEffect(() => {
    let active = true
    adminOperationsApi.catalogue().then(rows => { if (active) setItems(rows.map(toInventoryItem)) })
      .catch(cause => { if (active) setError((cause as Error).message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const mutate = async (action: () => Promise<void>) => {
    if (mutationLock.current) return
    mutationLock.current = true; setBusy(true); setError('')
    try { await action() }
    catch (cause) { setError((cause as Error).message); onShowToast?.('Catalogue update failed', (cause as Error).message, 'error') }
    finally { mutationLock.current = false; setBusy(false) }
  }

  // New Item Form State
  const [formName, setFormName] = useState('')
  const [formCategory, setFormCategory] = useState<AlaCarteItem['category']>('Snacks')
  const [formPrice, setFormPrice] = useState('100')
  const [formTiming, setFormTiming] = useState('all_day')
  const [formVeg, setFormVeg] = useState(true)
  const [formAvailable, setFormAvailable] = useState(true)

  const handleToggleAvailability = (id: string) => {
    const item = items.find(row => row.id === id)
    if (!item) return
    void mutate(async () => {
      const updated = await adminOperationsApi.availability(id, !item.is_available)
      setItems(prev => prev.map(row => row.id === id ? toInventoryItem(updated) : row))
      onShowToast?.(updated.available ? 'Item is Now Available' : 'Item Marked Sold Out', updated.name + ' availability saved.', 'success')
    })
  }

  const handleOpenAddModal = () => {
    if (loading || busy) return
    setFormDescription(''); setFormPrep('10')
    setEditingItem(null)
    setFormName('')
    setFormCategory('Snacks')
    setFormPrice('100')
    setFormTiming('all_day')
    setFormVeg(true)
    setFormAvailable(true)
    setIsModalOpen(true)
  }

  const handleOpenEditModal = (item: AlaCarteItem) => {
    if (busy) return
    setFormDescription(item.source.desc); setFormPrep(String(item.prep_time_mins))
    setEditingItem(item)
    setFormName(item.item_name)
    setFormCategory(item.category)
    setFormPrice(item.price.toString())
    setFormTiming(item.timing_window)
    setFormVeg(item.veg)
    setFormAvailable(item.is_available)
    setIsModalOpen(true)
  }

  const handleSaveItem = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) return
    const price = Number(formPrice), prepMins = Number(formPrep)
    if (!Number.isFinite(price) || price <= 0 || !Number.isInteger(prepMins) || prepMins < 1) { setError('Enter a positive price and preparation time.'); return }
    void mutate(async () => {
      const payload = { name: formName.trim(), desc: formDescription.trim(), category: formCategory, price,
        timingWindow: formTiming, veg: formVeg, available: formAvailable, prepMins,
        emoji: editingItem?.source.emoji || (formCategory === 'Beverages' ? '🥤' : formCategory === 'Desserts' ? '🧁' : '🍽️'),
        photo: editingItem?.source.photo || '', customizations: editingItem?.source.customizations || [] }
      const saved = editingItem ? await adminOperationsApi.updateItem(editingItem.id, payload) : await adminOperationsApi.createItem(payload)
      setItems(prev => editingItem ? prev.map(row => row.id === saved.id ? toInventoryItem(saved) : row) : [toInventoryItem(saved), ...prev])
      setIsModalOpen(false)
      onShowToast?.(editingItem ? 'Item Updated' : 'New Item Added', saved.name + ' saved to the student catalogue.', 'success')
    })
  }
  const handleDeleteItem = (id: string, name: string) => {
    if (busy || !confirm('Disable "' + name + '" in the student catalogue? Existing order history will be preserved.')) return
    void mutate(async () => {
      await adminOperationsApi.removeItem(id)
      const rows = await adminOperationsApi.catalogue()
      setItems(rows.map(toInventoryItem))
      onShowToast?.('Item Disabled', name + ' is no longer available for ordering.', 'info')
    })
  }

  // Filter Items
  const filteredItems = items.filter((item) => {
    const matchesSearch = item.item_name.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = selectedCategory === 'All' || item.category === selectedCategory
    const matchesTiming =
      selectedTimingFilter === 'all' ||
      (selectedTimingFilter === 'all_day' && item.timing_window === 'all_day') ||
      (selectedTimingFilter !== 'all_day' && item.timing_window.includes(selectedTimingFilter))
    return matchesSearch && matchesCategory && matchesTiming
  })

  const availableCount = items.filter((i) => i.is_available).length
  const soldOutCount = items.length - availableCount

  return (
    <div className="space-y-8 max-w-6xl mx-auto" aria-busy={busy || loading}>
      {loading && <p role="status" className="text-sm text-stone-500">Loading student catalogue…</p>}
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-white p-4 text-sm text-red-700">{error}</p>}
      {/* Top Stat Cards & Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-stone-600">
              Total Catalog Items
            </p>
            <h4 className="text-3xl font-extrabold text-[#1D1A16] mt-1">
              {items.length}
            </h4>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-stone-100 border border-stone-200 flex items-center justify-center text-xl">
            📋
          </div>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-stone-600">
              Active & Serving
            </p>
            <h4 className="text-3xl font-extrabold text-emerald-700 mt-1">
              {availableCount}
            </h4>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center text-xl">
            ✓
          </div>
        </div>

        <div className="p-6 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-stone-600">
              Sold Out / Inactive
            </p>
            <h4 className="text-3xl font-extrabold text-stone-500 mt-1">
              {soldOutCount}
            </h4>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-stone-100 border border-stone-200 text-stone-400 flex items-center justify-center text-xl">
            ✕
          </div>
        </div>
      </div>

      {/* Control Bar: Search, Category Filters, and Add Button */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Search Bar */}
        <div className="relative flex-1 max-w-md">
          <svg
            className="w-4 h-4 text-stone-400 absolute left-4 top-1/2 -translate-y-1/2"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search dish name, timing, or category..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-11 pr-4 py-2.5 rounded-full bg-white border border-[#E5DFD7] focus:border-[#F25C2C] focus:ring-2 focus:ring-[#F25C2C]/10 text-xs font-medium text-[#1D1A16] placeholder:text-stone-400 outline-none transition-all shadow-2xs"
          />
        </div>

        {/* Action button */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleOpenAddModal}
          disabled={busy || loading}
            className="px-6 py-2.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-md shadow-[#F25C2C]/25 active:scale-95 cursor-pointer flex items-center gap-2"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2.5"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            <span>Add New Item</span>
          </button>
        </div>
      </div>

      {/* Category Pills Filter */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
        {['All', 'Snacks', 'Meals', 'Beverages', 'Quick Bites', 'Desserts'].map((cat) => {
          const isSelected = selectedCategory === cat
          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all whitespace-nowrap cursor-pointer ${
                isSelected
                  ? 'bg-[#1D1A16] text-white shadow-sm'
                  : 'bg-white text-stone-600 hover:bg-stone-50 border border-[#E5DFD7]'
              }`}
            >
              {cat}
            </button>
          )
        })}
      </div>

      {/* Widely Spaced Table / List in a Crisp White Card */}
      <div className="rounded-3xl bg-white border border-[#E5DFD7] shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#E5DFD7] bg-[#FAF7F3]/60 text-[11px] font-bold uppercase tracking-wider text-stone-600">
                <th className="py-4 px-6">Dish Details</th>
                <th className="py-4 px-6">Category</th>
                <th className="py-4 px-6">Timing Window</th>
                <th className="py-4 px-6">Price</th>
                <th className="py-4 px-6">Today Orders</th>
                <th className="py-4 px-6 text-center">Availability Toggle</th>
                <th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5DFD7]/80 text-xs font-medium text-[#1D1A16]">
              {filteredItems.length > 0 ? (
                filteredItems.map((item) => {
                  return (
                    <tr
                      key={item.id}
                      className="hover:bg-[#FAF7F3]/50 transition-colors group"
                    >
                      {/* Dish Details */}
                      <td className="py-5 px-6">
                        <div className="flex items-center gap-3.5">
                          <div className="w-11 h-11 rounded-2xl bg-stone-100 border border-[#E5DFD7] flex items-center justify-center text-2xl shrink-0 shadow-2xs">
                            {item.emoji || '🍽️'}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span
                                className={`w-3.5 h-3.5 rounded-sm flex items-center justify-center border ${
                                  item.veg ? 'border-emerald-600' : 'border-rose-600'
                                }`}
                                title={item.veg ? 'Vegetarian' : 'Non-Vegetarian'}
                              >
                                <span
                                  className={`w-1.5 h-1.5 rounded-full ${
                                    item.veg ? 'bg-emerald-600' : 'bg-rose-600'
                                  }`}
                                />
                              </span>
                              <p className="font-bold text-sm text-[#1D1A16] group-hover:text-[#F25C2C] transition-colors">
                                {item.item_name}
                              </p>
                            </div>
                            <p className="text-[11px] text-stone-500 mt-0.5">
                              Avg Prep: {item.prep_time_mins} mins
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Category */}
                      <td className="py-5 px-6">
                        <span className="px-3 py-1 rounded-full bg-stone-100 text-stone-700 text-[11px] font-semibold border border-stone-200">
                          {item.category}
                        </span>
                      </td>

                      {/* Timing Window */}
                      <td className="py-5 px-6">
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200 text-[11px] font-semibold">
                          <svg
                            className="w-3.5 h-3.5 text-amber-600"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          </svg>
                          <span>
                            {item.timing_window === 'all_day'
                              ? 'All Day (24x7)'
                              : item.timing_window}
                          </span>
                        </span>
                      </td>

                      {/* Price */}
                      <td className="py-5 px-6 font-bold text-sm text-[#1D1A16]">
                        ₹{item.price.toFixed(2)}
                      </td>

                      {/* Orders */}
                      <td className="py-5 px-6 font-mono text-xs text-stone-600">
                        {item.orders_today ?? '—'} orders
                      </td>

                      {/* Modern Pill-Shaped Toggle Switch (Orange when active) */}
                      <td className="py-5 px-6">
                        <div className="flex flex-col items-center justify-center gap-1">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={item.is_available}
                            onClick={() => handleToggleAvailability(item.id)}
                      disabled={busy}
                            className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full p-0.5 transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#F25C2C]/20 shadow-inner ${
                              item.is_available ? 'bg-[#F25C2C]' : 'bg-stone-300'
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                                item.is_available ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                          <span
                            className={`text-[10px] font-bold uppercase tracking-wider ${
                              item.is_available ? 'text-[#F25C2C]' : 'text-stone-400'
                            }`}
                          >
                            {item.is_available ? 'Available' : 'Sold Out'}
                          </span>
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-5 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleOpenEditModal(item)}
                        disabled={busy}
                            className="p-2 rounded-xl bg-stone-100 hover:bg-stone-200 text-stone-700 transition-colors cursor-pointer"
                            title="Edit Item"
                          >
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                              />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleDeleteItem(item.id, item.item_name)}
                        disabled={busy}
                            className="p-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-600 transition-colors cursor-pointer"
                            title="Delete Item"
                          >
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                              />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    No items match the current search or filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit Item Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-[sco-rise_0.2s_ease-out]">
          <div className="w-full max-w-lg rounded-3xl bg-white border border-[#E5DFD7] p-8 shadow-2xl space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-[#E5DFD7]">
              <div>
                <h4 className="text-lg font-bold text-[#1D1A16]">
                  {editingItem ? 'Edit A La Carte Dish' : 'Add New A La Carte Dish'}
                </h4>
                <p className="text-xs text-stone-500 mt-0.5">
                  Changes will be synchronized with PostgreSQL and students' live menus.
                </p>
              </div>
              <button
                onClick={() => { if (!busy) setIsModalOpen(false) }}
                className="w-8 h-8 rounded-full bg-stone-100 hover:bg-stone-200 text-stone-600 flex items-center justify-center text-xs font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveItem} className="space-y-4">
              {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <label className="text-xs font-bold text-stone-700">Description<input value={formDescription} onChange={e => setFormDescription(e.target.value)} className="mt-1 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-3 text-sm font-normal" /></label>
                <label className="text-xs font-bold text-stone-700">Preparation (minutes)<input type="number" min="1" max="120" required value={formPrep} onChange={e => setFormPrep(e.target.value)} className="mt-1 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-3 text-sm font-normal" /></label>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-stone-600 mb-1.5">
                  Item Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Paneer Tikka Roll"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-[#FAF7F3] border border-[#E5DFD7] focus:border-[#F25C2C] focus:bg-white text-xs font-semibold text-[#1D1A16] outline-none transition-all"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-stone-600 mb-1.5">
                    Category
                  </label>
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value as AlaCarteItem['category'])}
                    className="w-full px-4 py-2.5 rounded-xl bg-[#FAF7F3] border border-[#E5DFD7] focus:border-[#F25C2C] focus:bg-white text-xs font-semibold text-[#1D1A16] outline-none cursor-pointer"
                  >
                    <option value="Snacks">Snacks</option>
                    <option value="Meals">Meals</option>
                    <option value="Beverages">Beverages</option>
                    <option value="Quick Bites">Quick Bites</option>
                    <option value="Desserts">Desserts</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-stone-600 mb-1.5">
                    Unit Price (₹)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    required
                    value={formPrice}
                    onChange={(e) => setFormPrice(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl bg-[#FAF7F3] border border-[#E5DFD7] focus:border-[#F25C2C] focus:bg-white text-xs font-semibold text-[#1D1A16] outline-none transition-all"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-stone-600 mb-1.5">
                  Timing Window
                </label>
                <select
                  value={formTiming}
                  onChange={(e) => setFormTiming(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-[#FAF7F3] border border-[#E5DFD7] focus:border-[#F25C2C] focus:bg-white text-xs font-semibold text-[#1D1A16] outline-none cursor-pointer"
                >
                  <option value="all_day">All Day (00:00 - 23:59)</option>
                  <option value="08:00-11:00">Breakfast Window (08:00 - 11:00)</option>
                  <option value="12:00-15:00">Lunch Window (12:00 - 15:00)</option>
                  <option value="16:30-18:30">Snacks Window (16:30 - 18:30)</option>
                  <option value="19:30-22:30">Dinner Window (19:30 - 22:30)</option>
                  <option value="12:00-22:30">Lunch to Dinner (12:00 - 22:30)</option>
                </select>
              </div>

              <div className="flex items-center justify-between p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                <span className="text-xs font-bold text-[#1D1A16]">
                  Vegetarian Preparation
                </span>
                <button
                  type="button"
                  onClick={() => setFormVeg(!formVeg)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full p-0.5 transition-colors duration-200 ${
                    formVeg ? 'bg-emerald-600' : 'bg-stone-300'
                  }`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${
                      formVeg ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                <div>
                  <p className="text-xs font-bold text-[#1D1A16]">Initial Availability</p>
                  <p className="text-[11px] text-stone-500">Enable item for ordering immediately</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormAvailable(!formAvailable)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full p-0.5 transition-colors duration-200 ${
                    formAvailable ? 'bg-[#F25C2C]' : 'bg-stone-300'
                  }`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${
                      formAvailable ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#E5DFD7]">
                <button
                  type="button"
                  onClick={() => { if (!busy) setIsModalOpen(false) }}
                  className="px-5 py-2.5 rounded-full bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-bold transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit" disabled={busy}
                  className="px-6 py-2.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-md shadow-[#F25C2C]/25 cursor-pointer"
                >
                  {busy ? 'Saving…' : editingItem ? 'Update Dish' : 'Save Dish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
