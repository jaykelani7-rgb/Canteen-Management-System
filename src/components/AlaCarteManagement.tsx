import React, { useState } from 'react'

export interface AlaCarteItem {
  id: number
  item_name: string
  category: 'Snacks' | 'Meals' | 'Beverages' | 'Desserts' | 'Quick Bites'
  price: number
  timing_window: string
  is_available: boolean
  veg: boolean
  orders_today: number
  prep_time_mins: number
  emoji?: string
}

interface AlaCarteManagementProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

const INITIAL_ITEMS: AlaCarteItem[] = [
  {
    id: 1,
    item_name: 'Paneer Butter Masala (Single)',
    category: 'Meals',
    price: 160.0,
    timing_window: '12:00-22:30',
    is_available: true,
    veg: true,
    orders_today: 42,
    prep_time_mins: 15,
    emoji: '🍛',
  },
  {
    id: 2,
    item_name: 'Crispy Peri-Peri French Fries',
    category: 'Snacks',
    price: 85.0,
    timing_window: 'all_day',
    is_available: true,
    veg: true,
    orders_today: 78,
    prep_time_mins: 8,
    emoji: '🍟',
  },
  {
    id: 3,
    item_name: 'Chicken Tikka Roll (Double Egg)',
    category: 'Quick Bites',
    price: 150.0,
    timing_window: '12:00-22:00',
    is_available: true,
    veg: false,
    orders_today: 56,
    prep_time_mins: 12,
    emoji: '🌯',
  },
  {
    id: 4,
    item_name: 'Veg Cheese Grill Sandwich',
    category: 'Snacks',
    price: 110.0,
    timing_window: '08:00-22:00',
    is_available: true,
    veg: true,
    orders_today: 34,
    prep_time_mins: 10,
    emoji: '🥪',
  },
  {
    id: 5,
    item_name: 'Cold Coffee with Vanilla Ice Cream',
    category: 'Beverages',
    price: 75.0,
    timing_window: 'all_day',
    is_available: true,
    veg: true,
    orders_today: 92,
    prep_time_mins: 5,
    emoji: '🥤',
  },
  {
    id: 6,
    item_name: 'Double Masala Cheese Maggi',
    category: 'Quick Bites',
    price: 65.0,
    timing_window: 'all_day',
    is_available: false,
    veg: true,
    orders_today: 19,
    prep_time_mins: 7,
    emoji: '🍜',
  },
  {
    id: 7,
    item_name: 'Fresh Mosambi Orange Juice',
    category: 'Beverages',
    price: 60.0,
    timing_window: '08:00-18:00',
    is_available: true,
    veg: true,
    orders_today: 28,
    prep_time_mins: 4,
    emoji: '🍊',
  },
  {
    id: 8,
    item_name: 'Warm Choco Lava Cake',
    category: 'Desserts',
    price: 90.0,
    timing_window: '12:00-22:30',
    is_available: false,
    veg: true,
    orders_today: 12,
    prep_time_mins: 5,
    emoji: '🧁',
  },
]

export default function AlaCarteManagement({ onShowToast }: AlaCarteManagementProps) {
  const [items, setItems] = useState<AlaCarteItem[]>(INITIAL_ITEMS)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('All')
  const [selectedTimingFilter, setSelectedTimingFilter] = useState<string>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<AlaCarteItem | null>(null)

  // New Item Form State
  const [formName, setFormName] = useState('')
  const [formCategory, setFormCategory] = useState<AlaCarteItem['category']>('Snacks')
  const [formPrice, setFormPrice] = useState('100')
  const [formTiming, setFormTiming] = useState('all_day')
  const [formVeg, setFormVeg] = useState(true)
  const [formAvailable, setFormAvailable] = useState(true)

  // Toggle item availability with modern pill switch
  const handleToggleAvailability = (id: number) => {
    setItems((prev) =>
      prev.map((item) => {
        if (item.id === id) {
          const nextState = !item.is_available
          onShowToast?.(
            nextState ? 'Item is Now Available' : 'Item Marked Sold Out',
            `"${item.item_name}" status updated in real-time. Students will see immediate change.`,
            nextState ? 'success' : 'warning'
          )
          return { ...item, is_available: nextState }
        }
        return item
      })
    )
  }

  const handleOpenAddModal = () => {
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

    const priceNum = parseFloat(formPrice) || 0

    if (editingItem) {
      setItems((prev) =>
        prev.map((item) =>
          item.id === editingItem.id
            ? {
                ...item,
                item_name: formName.trim(),
                category: formCategory,
                price: priceNum,
                timing_window: formTiming,
                veg: formVeg,
                is_available: formAvailable,
              }
            : item
        )
      )
      onShowToast?.('Item Updated', `"${formName}" has been successfully modified.`, 'success')
    } else {
      const newItem: AlaCarteItem = {
        id: Date.now(),
        item_name: formName.trim(),
        category: formCategory,
        price: priceNum,
        timing_window: formTiming,
        is_available: formAvailable,
        veg: formVeg,
        orders_today: 0,
        prep_time_mins: 10,
        emoji: formCategory === 'Beverages' ? '🥤' : formCategory === 'Desserts' ? '🧁' : '🍽️',
      }
      setItems((prev) => [newItem, ...prev])
      onShowToast?.('New Item Added', `"${formName}" added to A La Carte catalog.`, 'success')
    }
    setIsModalOpen(false)
  }

  const handleDeleteItem = (id: number, name: string) => {
    if (confirm(`Are you sure you want to remove "${name}" from A La Carte?`)) {
      setItems((prev) => prev.filter((item) => item.id !== id))
      onShowToast?.('Item Removed', `"${name}" was deleted from inventory.`, 'info')
    }
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
    <div className="space-y-8 max-w-6xl mx-auto">
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
                        {item.orders_today} orders
                      </td>

                      {/* Modern Pill-Shaped Toggle Switch (Orange when active) */}
                      <td className="py-5 px-6">
                        <div className="flex flex-col items-center justify-center gap-1">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={item.is_available}
                            onClick={() => handleToggleAvailability(item.id)}
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
                onClick={() => setIsModalOpen(false)}
                className="w-8 h-8 rounded-full bg-stone-100 hover:bg-stone-200 text-stone-600 flex items-center justify-center text-xs font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveItem} className="space-y-4">
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
                  onClick={() => setIsModalOpen(false)}
                  className="px-5 py-2.5 rounded-full bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-bold transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-md shadow-[#F25C2C]/25 cursor-pointer"
                >
                  {editingItem ? 'Update Dish' : 'Save Dish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
